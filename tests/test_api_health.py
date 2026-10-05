from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _client(database_url: str) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(create_app(settings=settings, engine=engine))


def test_health_returns_healthy_report(migrated_database_url: str) -> None:
    response = _client(migrated_database_url).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "HEALTHY"
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"


def test_health_returns_503_when_database_unavailable(unavailable_database_url: str) -> None:
    response = _client(unavailable_database_url).get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "UNHEALTHY"
    codes = [check["error"]["code"] for check in body["checks"] if "error" in check]
    assert "RAD-DB-003" in codes


def test_health_honors_caller_correlation_id(migrated_database_url: str) -> None:
    response = _client(migrated_database_url).get(
        "/health", headers={"X-Correlation-ID": "caller-correlation"}
    )
    assert response.json()["correlation_id"] == "caller-correlation"
    assert response.headers["x-correlation-id"] == "caller-correlation"


def test_version_contract(migrated_database_url: str) -> None:
    response = _client(migrated_database_url).get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["app_version"]
