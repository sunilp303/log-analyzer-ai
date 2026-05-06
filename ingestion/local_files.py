import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import List

from langchain_core.documents import Document

_LEVEL_RE = re.compile(
    r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRIT(?:ICAL)?|FATAL)\b", re.IGNORECASE
)
_TS_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?"
)
_SERVICE_RE = re.compile(r"\b([a-z][a-z0-9-]+(?:-service|gateway|db|kafka))\b")


def _extract_level(message: str) -> str:
    m = _LEVEL_RE.search(message)
    return m.group(1).upper() if m else "INFO"


def _extract_timestamp(message: str) -> str:
    m = _TS_RE.search(message)
    return m.group(0) if m else datetime.now(timezone.utc).isoformat()


def _extract_service(message: str, filename: str) -> str:
    m = _SERVICE_RE.search(message)
    if m:
        return m.group(1)
    return Path(filename).stem


def _plain_log_to_document(line: str, source_path: str) -> Document:
    return Document(
        page_content=line.strip(),
        metadata={
            "source": "local",
            "file": source_path,
            "timestamp": _extract_timestamp(line),
            "level": _extract_level(line),
            "service": _extract_service(line, source_path),
            "log_group": str(Path(source_path).parent),
        },
    )


def _elk_hit_to_document(hit: dict, source_path: str) -> Document:
    src = hit.get("_source", {})
    message = src.get("message", json.dumps(src))
    return Document(
        page_content=message,
        metadata={
            "source": "local",
            "file": source_path,
            "timestamp": src.get("@timestamp", ""),
            "level": src.get("level", "INFO"),
            "service": src.get("service", "unknown"),
            "log_group": src.get("_index", ""),
            "host": src.get("host", ""),
        },
    )


def _cloudwatch_event_to_document(event: dict, source_path: str) -> Document:
    ts_ms = event.get("timestamp", 0)
    ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
    stream = event.get("logStreamName", "")
    service = stream.split("/")[0] if "/" in stream else stream
    return Document(
        page_content=event.get("message", ""),
        metadata={
            "source": "local",
            "file": source_path,
            "timestamp": ts,
            "level": _extract_level(event.get("message", "")),
            "service": service,
            "log_group": stream,
        },
    )


def load_local_logs(path: str) -> List[Document]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    suffix = p.suffix.lower()

    if suffix == ".log":
        lines = p.read_text(encoding="utf-8").splitlines()
        return [
            _plain_log_to_document(line, str(p))
            for line in lines
            if line.strip()
        ]

    if suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))

        if isinstance(data, list):
            if data and "@timestamp" in data[0]:
                return [_elk_hit_to_document({"_source": item}, str(p)) for item in data]
            if data and "timestamp" in data[0]:
                return [_cloudwatch_event_to_document(item, str(p)) for item in data]
            return [
                Document(
                    page_content=json.dumps(item),
                    metadata={"source": "local", "file": str(p), "timestamp": "", "level": "INFO", "service": "unknown", "log_group": ""},
                )
                for item in data
            ]

        if "hits" in data:
            hits = data["hits"].get("hits", [])
            return [_elk_hit_to_document(h, str(p)) for h in hits]

        if "events" in data:
            return [_cloudwatch_event_to_document(e, str(p)) for e in data["events"]]

        return [Document(page_content=json.dumps(data), metadata={"source": "local", "file": str(p), "timestamp": "", "level": "INFO", "service": "unknown", "log_group": ""})]

    if suffix == ".ndjson":
        docs = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            message = item.get("message", line)
            docs.append(Document(
                page_content=message,
                metadata={
                    "source": "local",
                    "file": str(p),
                    "timestamp": item.get("@timestamp", item.get("timestamp", "")),
                    "level": item.get("level", _extract_level(message)),
                    "service": item.get("service", "unknown"),
                    "log_group": "",
                },
            ))
        return docs

    raise ValueError(f"Unsupported file type: {suffix}. Use .log, .json, or .ndjson")
