import json
from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models import BaseChatModel
from langchain_community.vectorstores import FAISS
from pydantic import BaseModel

from llm.providers import get_llm
from analysis.anomaly import analyze_anomalies
from analysis.correlation import correlate_services
from analysis.summarizer import summarize_window


class TimelineEvent(BaseModel):
    timestamp: str
    service: str
    event: str
    severity: str


class PostMortem(BaseModel):
    title: str
    timeline: List[TimelineEvent]
    root_cause: str
    impact: str
    remediation_steps: List[str]
    open_questions: List[str]


_SYSTEM = """You are a senior SRE writing a structured post-mortem report.
Using the provided anomaly findings, correlation analysis, and incident summary,
produce a thorough post-mortem. Be specific, reference service names and timestamps,
and ensure remediation steps are actionable."""

_HUMAN = """Incident Summary:
{summary}

Anomaly Report:
{anomalies}

Service Correlation:
{correlation}

Generate a complete post-mortem report."""

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", _HUMAN),
])


def generate_postmortem(
    documents: List[Document],
    services: Optional[List[str]] = None,
    vectorstore: Optional[FAISS] = None,
    llm: Optional[BaseChatModel] = None,
) -> PostMortem:
    if llm is None:
        llm = get_llm()

    anomaly_report = analyze_anomalies(documents, llm=llm)
    correlation = correlate_services(documents, services=services, vectorstore=vectorstore, llm=llm)
    summary = summarize_window(documents, llm=llm)

    structured_llm = llm.with_structured_output(PostMortem)
    chain = _PROMPT | structured_llm

    return chain.invoke({
        "summary": summary,
        "anomalies": json.dumps(anomaly_report.model_dump(), indent=2),
        "correlation": correlation,
    })


def postmortem_to_markdown(pm: PostMortem) -> str:
    lines = [
        f"# Post-Mortem: {pm.title}",
        "",
        "## Timeline",
        "",
        "| Timestamp | Service | Event | Severity |",
        "|-----------|---------|-------|----------|",
    ]
    for e in pm.timeline:
        lines.append(f"| {e.timestamp} | {e.service} | {e.event} | {e.severity} |")

    lines += [
        "",
        "## Root Cause",
        "",
        pm.root_cause,
        "",
        "## Impact",
        "",
        pm.impact,
        "",
        "## Remediation Steps",
        "",
    ]
    for i, step in enumerate(pm.remediation_steps, 1):
        lines.append(f"{i}. {step}")

    lines += [
        "",
        "## Open Questions",
        "",
    ]
    for q in pm.open_questions:
        lines.append(f"- {q}")

    return "\n".join(lines)
