"""Tests for all three ingestion loaders using sample data files."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

SAMPLE_DIR = Path(__file__).parent.parent / "sample_logs"


# ── Local file ingestion ──────────────────────────────────────────────────────

class TestLocalFiles:
    def test_load_plain_log(self):
        from ingestion.local_files import load_local_logs

        docs = load_local_logs(str(SAMPLE_DIR / "app_errors.log"))

        assert len(docs) > 0
        for doc in docs:
            assert isinstance(doc, Document)
            assert doc.page_content.strip()
            assert "source" in doc.metadata
            assert doc.metadata["source"] == "local"
            assert "timestamp" in doc.metadata
            assert "service" in doc.metadata
            assert "level" in doc.metadata

    def test_load_plain_log_detects_levels(self):
        from ingestion.local_files import load_local_logs

        docs = load_local_logs(str(SAMPLE_DIR / "app_errors.log"))
        levels = {d.metadata["level"] for d in docs}
        assert "ERROR" in levels or "CRIT" in levels

    def test_load_cloudwatch_json(self):
        from ingestion.local_files import load_local_logs

        docs = load_local_logs(str(SAMPLE_DIR / "cloudwatch_sample.json"))

        assert len(docs) > 0
        for doc in docs:
            assert isinstance(doc, Document)
            assert doc.page_content.strip()
            assert doc.metadata["source"] == "local"
            assert doc.metadata.get("timestamp")
            assert doc.metadata.get("service")

    def test_load_elk_json(self):
        from ingestion.local_files import load_local_logs

        docs = load_local_logs(str(SAMPLE_DIR / "elk_sample.json"))

        assert len(docs) > 0
        for doc in docs:
            assert isinstance(doc, Document)
            assert doc.page_content.strip()
            assert doc.metadata["source"] == "local"

    def test_file_not_found_raises(self):
        from ingestion.local_files import load_local_logs

        with pytest.raises(FileNotFoundError):
            load_local_logs("/nonexistent/path/file.log")

    def test_unsupported_extension_raises(self):
        from ingestion.local_files import load_local_logs
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"col1,col2\nval1,val2\n")
            tmp = f.name

        try:
            with pytest.raises(ValueError, match="Unsupported file type"):
                load_local_logs(tmp)
        finally:
            os.unlink(tmp)

    def test_ndjson_loading(self, tmp_path):
        from ingestion.local_files import load_local_logs

        ndjson_file = tmp_path / "test.ndjson"
        lines = [
            json.dumps({"@timestamp": "2026-05-06T13:45:00Z", "level": "ERROR", "service": "api", "message": "Connection refused"}),
            json.dumps({"@timestamp": "2026-05-06T13:45:01Z", "level": "INFO", "service": "api", "message": "Retry attempt 1"}),
        ]
        ndjson_file.write_text("\n".join(lines))

        docs = load_local_logs(str(ndjson_file))
        assert len(docs) == 2
        assert docs[0].metadata["service"] == "api"
        assert docs[0].metadata["level"] == "ERROR"


# ── CloudWatch ingestion ──────────────────────────────────────────────────────

class TestCloudWatch:
    def test_fetch_cloudwatch_logs(self):
        from ingestion.cloudwatch import fetch_cloudwatch_logs

        mock_events = [
            {
                "logStreamName": "api-gateway/prod/i-001",
                "timestamp": 1746534301123,
                "message": "[ERROR] upstream connection refused",
                "ingestionTime": 1746534301200,
                "eventId": "evt-001",
            },
            {
                "logStreamName": "auth-service/prod/i-002",
                "timestamp": 1746534313678,
                "message": "[CRIT] DB pool exhausted",
                "ingestionTime": 1746534313800,
                "eventId": "evt-002",
            },
        ]

        mock_page = {"events": mock_events}
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [mock_page]
        mock_client = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator

        with patch("ingestion.cloudwatch._make_client", return_value=mock_client):
            docs = fetch_cloudwatch_logs(log_group="/app/prod", hours=2)

        assert len(docs) == 2
        assert docs[0].metadata["source"] == "cloudwatch"
        assert docs[0].metadata["log_group"] == "/app/prod"
        assert docs[0].metadata["timestamp"]
        assert docs[1].metadata["level"] == "CRIT"

    def test_cloudwatch_error_level_extraction(self):
        from ingestion.cloudwatch import _extract_level

        assert _extract_level("[ERROR] something went wrong") == "ERROR"
        assert _extract_level("[WARN] high latency") == "WARN"
        assert _extract_level("[INFO] all good") == "INFO"
        assert _extract_level("no level marker here") == "INFO"


# ── Elasticsearch ingestion ───────────────────────────────────────────────────

class TestElasticsearch:
    def test_fetch_elk_logs(self):
        from ingestion.elasticsearch import fetch_elk_logs

        mock_response = {
            "hits": {
                "hits": [
                    {
                        "_index": "app-logs-2026.05.06",
                        "_id": "log-001",
                        "_score": 1.0,
                        "_source": {
                            "@timestamp": "2026-05-06T13:45:13.678Z",
                            "level": "ERROR",
                            "service": "auth-service",
                            "host": "i-001",
                            "message": "DB pool exhausted",
                        },
                    }
                ]
            }
        }

        mock_client = MagicMock()
        mock_client.search.return_value = mock_response

        with patch("ingestion.elasticsearch._make_client", return_value=mock_client):
            docs = fetch_elk_logs(index="app-logs-*", hours=2)

        assert len(docs) == 1
        doc = docs[0]
        assert doc.metadata["source"] == "elk"
        assert doc.metadata["service"] == "auth-service"
        assert doc.metadata["level"] == "ERROR"
        assert doc.metadata["timestamp"] == "2026-05-06T13:45:13.678Z"
        assert doc.page_content == "DB pool exhausted"
