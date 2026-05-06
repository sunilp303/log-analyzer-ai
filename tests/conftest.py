import json
import pytest
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

SAMPLE_DIR = Path(__file__).parent.parent / "sample_logs"


@pytest.fixture
def sample_documents():
    return [
        Document(
            page_content="[ERROR] [auth-003] Database connection pool exhausted pool_size=20 active=20 waiting=47",
            metadata={"source": "local", "timestamp": "2026-05-06T13:45:13.678Z", "service": "auth-service", "level": "ERROR", "log_group": ""},
        ),
        Document(
            page_content="[WARN] [auth-006] Circuit breaker OPEN for db-primary after 5 consecutive failures",
            metadata={"source": "local", "timestamp": "2026-05-06T13:45:14.456Z", "service": "auth-service", "level": "WARN", "log_group": ""},
        ),
        Document(
            page_content="[CRIT] Max connections reached max_connections=500 current=498 - rejecting new connections",
            metadata={"source": "local", "timestamp": "2026-05-06T13:45:17.123Z", "service": "db-primary", "level": "CRIT", "log_group": ""},
        ),
        Document(
            page_content="[ERROR] [pay-001] Health check failed: unable to reach db-primary connection_error=timeout",
            metadata={"source": "local", "timestamp": "2026-05-06T13:45:20.678Z", "service": "payment-service", "level": "ERROR", "log_group": ""},
        ),
        Document(
            page_content="[ERROR] [ord-005] All retries exhausted payment-service unavailable - marking order_id=78432 FAILED",
            metadata={"source": "local", "timestamp": "2026-05-06T13:45:16.567Z", "service": "order-service", "level": "ERROR", "log_group": ""},
        ),
        Document(
            page_content="[CRIT] [gw-health] Health check cascade: auth-service=DOWN order-service=DEGRADED payment-service=DOWN",
            metadata={"source": "local", "timestamp": "2026-05-06T13:45:30.345Z", "service": "api-gateway", "level": "CRIT", "log_group": ""},
        ),
    ]


@pytest.fixture
def fake_anomaly_response():
    return json.dumps({
        "anomalies": [
            {
                "severity": "critical",
                "type": "database_exhaustion",
                "description": "DB connection pool exhausted causing cascade",
                "evidence": ["Database connection pool exhausted pool_size=20"],
                "affected_services": ["auth-service", "db-primary"],
            }
        ],
        "summary": "Critical database exhaustion triggered a cascading failure.",
    })


@pytest.fixture
def fake_postmortem_response():
    return json.dumps({
        "title": "DB Connection Pool Exhaustion — 2026-05-06",
        "timeline": [
            {"timestamp": "2026-05-06T13:45:13Z", "service": "db-primary", "event": "Connection pool exhausted", "severity": "critical"},
            {"timestamp": "2026-05-06T13:45:14Z", "service": "auth-service", "event": "Circuit breaker opened", "severity": "high"},
        ],
        "root_cause": "The database connection pool was exhausted due to a slow query storm.",
        "impact": "Auth, payment, and order services were unavailable for ~90 seconds.",
        "remediation_steps": [
            "Increase connection pool size",
            "Add query timeout enforcement",
        ],
        "open_questions": [
            "What triggered the slow query storm?",
        ],
    })


@pytest.fixture
def fake_llm_str():
    return FakeListChatModel(responses=["This is a fake LLM summary response."])
