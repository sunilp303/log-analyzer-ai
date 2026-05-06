from typing import List, Literal, Optional

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from llm.providers import get_llm


class Anomaly(BaseModel):
    severity: Literal["critical", "high", "medium", "low"]
    type: str
    description: str
    evidence: List[str]
    affected_services: List[str]


class AnomalyReport(BaseModel):
    anomalies: List[Anomaly]
    summary: str


_SYSTEM = """You are a senior SRE analyzing production logs to detect anomalies.
Examine the logs carefully and identify ALL anomalies, including:
- Error spikes or repeated failures
- Latency degradation or timeouts
- Resource exhaustion (connections, memory, disk)
- Circuit breaker trips or cascading failures
- Authentication or authorization failures
- Missing heartbeats or health check failures

For each anomaly provide severity (critical/high/medium/low), a short type label,
a clear description, specific log lines as evidence, and which services are affected."""

_HUMAN = """Analyze these logs and return structured anomaly findings:

{logs}"""

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", _HUMAN),
])


def _format_logs(documents: List[Document]) -> str:
    lines = []
    for doc in documents:
        meta = doc.metadata
        ts = meta.get("timestamp", "")
        svc = meta.get("service", "")
        lvl = meta.get("level", "")
        lines.append(f"[{ts}] [{svc}] [{lvl}] {doc.page_content}")
    return "\n".join(lines)


def analyze_anomalies(
    documents: List[Document],
    llm: Optional[BaseChatModel] = None,
) -> AnomalyReport:
    if llm is None:
        llm = get_llm()

    structured_llm = llm.with_structured_output(AnomalyReport)
    chain = _PROMPT | structured_llm
    return chain.invoke({"logs": _format_logs(documents)})
