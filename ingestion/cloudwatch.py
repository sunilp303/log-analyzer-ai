from datetime import datetime, timedelta, timezone
from typing import List, Optional

from langchain_core.documents import Document

from config import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN


def _make_client():
    import boto3
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    if AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = AWS_SESSION_TOKEN
    return boto3.client("logs", **kwargs)


def _extract_level(message: str) -> str:
    import re
    m = re.search(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRIT(?:ICAL)?|FATAL)\b", message, re.IGNORECASE)
    return m.group(1).upper() if m else "INFO"


def fetch_cloudwatch_logs(
    log_group: str,
    hours: int = 2,
    log_stream: Optional[str] = None,
    filter_pattern: str = "",
) -> List[Document]:
    client = _make_client()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    kwargs = {
        "logGroupName": log_group,
        "startTime": int(start_time.timestamp() * 1000),
        "endTime": int(end_time.timestamp() * 1000),
    }
    if log_stream:
        kwargs["logStreamNames"] = [log_stream]
    if filter_pattern:
        kwargs["filterPattern"] = filter_pattern

    documents: List[Document] = []
    paginator = client.get_paginator("filter_log_events")

    for page in paginator.paginate(**kwargs):
        for event in page["events"]:
            ts = datetime.fromtimestamp(
                event["timestamp"] / 1000, tz=timezone.utc
            ).isoformat()
            stream = event.get("logStreamName", "")
            service = log_group.split("/")[-1] if "/" in log_group else log_group.lstrip("/")

            documents.append(Document(
                page_content=event["message"],
                metadata={
                    "source": "cloudwatch",
                    "log_group": log_group,
                    "log_stream": stream,
                    "timestamp": ts,
                    "level": _extract_level(event["message"]),
                    "service": service,
                    "event_id": event.get("eventId", ""),
                },
            ))

    return documents
