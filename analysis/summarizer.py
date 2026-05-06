from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseChatModel

from llm.providers import get_llm
from processing.chunker import chunk_documents


_MAP_SYSTEM = "You are summarizing a window of production logs. Be concise and focus on errors and anomalies."
_MAP_HUMAN = "Summarize the key events in this log chunk in 2-3 sentences:\n\n{chunk}"

_REDUCE_SYSTEM = """You are synthesizing multiple log summaries into one coherent incident summary.
Cover: what happened, which services were affected, the timeline, and severity."""
_REDUCE_HUMAN = "Combine these chunk summaries into a single paragraph summary:\n\n{summaries}"

_MAP_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _MAP_SYSTEM),
    ("human", _MAP_HUMAN),
])
_REDUCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _REDUCE_SYSTEM),
    ("human", _REDUCE_HUMAN),
])


def summarize_window(
    documents: List[Document],
    start: Optional[str] = None,
    end: Optional[str] = None,
    llm: Optional[BaseChatModel] = None,
) -> str:
    if llm is None:
        llm = get_llm()

    filtered = _filter_by_time(documents, start, end)
    if not filtered:
        filtered = documents

    chunks = chunk_documents(filtered, chunk_size=3000, chunk_overlap=100)

    map_chain = _MAP_PROMPT | llm | StrOutputParser()
    reduce_chain = _REDUCE_PROMPT | llm | StrOutputParser()

    chunk_summaries = [
        map_chain.invoke({"chunk": chunk.page_content})
        for chunk in chunks
    ]

    if len(chunk_summaries) == 1:
        return chunk_summaries[0]

    return reduce_chain.invoke({"summaries": "\n\n".join(chunk_summaries)})


def _filter_by_time(
    documents: List[Document],
    start: Optional[str],
    end: Optional[str],
) -> List[Document]:
    if not start and not end:
        return documents
    result = []
    for doc in documents:
        ts = doc.metadata.get("timestamp", "")
        if start and ts and ts < start:
            continue
        if end and ts and ts > end:
            continue
        result.append(doc)
    return result
