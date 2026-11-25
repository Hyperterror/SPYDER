"""
Tests for Structured Logging Redaction & Readiness/Liveness Probes (Milestone 6).
"""
import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.logging import JsonLogFormatter, redact_sensitive_text
from app.main import app


@pytest.fixture()
def obs_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = TestingSession()

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    db.close()


def test_structured_logging_redacts_secrets_and_bearer_tokens():
    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig password=SuperSecret123 token=tok_abc"
    masked = redact_sensitive_text(raw)
    assert "eyJhbGciOiJIUzI1NiJ9" not in masked
    assert "SuperSecret123" not in masked
    assert "tok_abc" not in masked
    assert "[REDACTED]" in masked

    formatter = JsonLogFormatter()
    rec = logging.LogRecord(
        name="spyder.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="User auth header Bearer abcdef12345 failed with password=my_pw",
        args=(),
        exc_info=None,
    )
    rec.extra_meta = {"password": "hidden", "raw_record": {"phone": "secret"}, "safe": "ok"}
    parsed = json.loads(formatter.format(rec))
    assert parsed["level"] == "INFO"
    assert "abcdef12345" not in parsed["message"]
    assert "my_pw" not in parsed["message"]
    assert parsed["meta"]["password"] == "[REDACTED]"
    assert parsed["meta"]["raw_record"] == "[REDACTED]"
    assert parsed["meta"]["safe"] == "ok"


def test_health_live_and_ready_endpoints_and_request_id(obs_client):
    r_health = obs_client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"
    assert "X-Request-ID" in r_health.headers

    r_live = obs_client.get("/health/live", headers={"X-Request-ID": "trace-xyz-123"})
    assert r_live.status_code == 200
    assert r_live.json()["status"] == "alive"
    assert r_live.headers["X-Request-ID"] == "trace-xyz-123"

    r_ready = obs_client.get("/health/ready")
    assert r_ready.status_code == 200
    body = r_ready.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["status"] == "up"
