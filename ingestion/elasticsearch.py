from datetime import datetime, timedelta, timezone
from typing import List, Optional

from langchain_core.documents import Document

from config import ES_HOST, ES_USERNAME, ES_PASSWORD, ES_VERIFY_CERTS


def _make_client():
    from elasticsearch import Elasticsearch

    kwargs: dict = {"hosts": [ES_HOST], "verify_certs": ES_VERIFY_CERTS}
    if ES_USERNAME:
        kwargs["http_auth"] = (ES_USERNAME, ES_PASSWORD)
    return Elasticsearch(**kwargs)


def fetch_elk_logs(
    index: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    hours: int = 2,
    services: Optional[List[str]] = None,
    size: int = 1000,
) -> List[Document]:
    client = _make_client()

    if end is None:
        end_dt = datetime.now(timezone.utc)
        end = end_dt.isoformat()
    else:
        end_dt = datetime.fromisoformat(end)

    if start is None:
        start = (end_dt - timedelta(hours=hours)).isoformat()

    range_filter: dict = {"@timestamp": {"gte": start, "lte": end}}
    filters = [{"range": range_filter}]

    if services:
        filters.append({"terms": {"service.keyword": services}})

    query = {
        "query": {"bool": {"filter": filters}},
        "sort": [{"@timestamp": {"order": "asc"}}],
        "size": size,
    }

    response = client.search(index=index, body=query)
    hits = response["hits"]["hits"]

    documents: List[Document] = []
    for hit in hits:
        src = hit["_source"]
        message = src.get("message", "")
        documents.append(Document(
            page_content=message,
            metadata={
                "source": "elk",
                "index": hit["_index"],
                "doc_id": hit["_id"],
                "timestamp": src.get("@timestamp", ""),
                "level": src.get("level", "INFO"),
                "service": src.get("service", "unknown"),
                "host": src.get("host", ""),
                "log_group": hit["_index"],
            },
        ))

    return documents
