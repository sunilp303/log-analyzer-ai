from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseChatModel
from langchain_community.vectorstores import FAISS

from llm.providers import get_llm


_SYSTEM = """You are a distributed systems expert analyzing cross-service error propagation.
Given logs from multiple services, identify:
1. The root service and event that triggered the incident
2. How the failure cascaded to downstream services (the causal chain)
3. Which services were affected and in what order
4. Any circular dependencies or amplification patterns

Be specific about timestamps and service names. Present findings as a clear narrative."""

_HUMAN = """Services involved: {services}

Relevant context from the log store:
{context}

Full log window:
{logs}

Identify the causal chain and cross-service correlations."""

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", _HUMAN),
])


def _format_docs(documents: List[Document]) -> str:
    lines = []
    for doc in documents:
        meta = doc.metadata
        ts = meta.get("timestamp", "")
        svc = meta.get("service", "")
        lvl = meta.get("level", "")
        lines.append(f"[{ts}] [{svc}] [{lvl}] {doc.page_content}")
    return "\n".join(lines)


def correlate_services(
    documents: List[Document],
    services: Optional[List[str]] = None,
    vectorstore: Optional[FAISS] = None,
    llm: Optional[BaseChatModel] = None,
) -> str:
    if llm is None:
        llm = get_llm()

    if services is None:
        services = list({d.metadata.get("service", "") for d in documents if d.metadata.get("service")})

    context_docs = documents
    if vectorstore is not None:
        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 15},
        )
        context_docs = retriever.invoke("service failure cascade error connection timeout")

    chain = _PROMPT | llm | StrOutputParser()
    return chain.invoke({
        "services": ", ".join(services),
        "context": _format_docs(context_docs),
        "logs": _format_docs(documents[:50]),
    })
