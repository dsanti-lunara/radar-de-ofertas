from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from radar.api.app import create_app
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract

_TABLES = (
    "product",
    "marketplace_product",
    "offer",
    "raw_capture",
    "evidence",
    "discovery_event",
    "candidate",
    "audit_event",
)


def _client(database_url: str) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(create_app(settings=settings, engine=engine))


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "marketplace": "MERCADO_LIVRE",
        "source": "BROWSER_EXTENSION",
        "product": {
            "external_id": "MLB123",
            "title": "Produto",
            "url": "https://www.mercadolivre.com.br/p/MLB123",
        },
        "offer": {
            "current_price": "79.90",
            "original_price": "109.90",
            "sales_count": 2300,
            "seller": {"name": "Loja"},
        },
        "captured_at": "2026-10-05T12:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def test_manual_capture_roundtrip(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.post(
        "/captures/manual", json=_payload(), headers={"X-Correlation-ID": "cid-api"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "CAPTURED"
    assert body["schema_version"] == "1.0"
    assert body["correlation_id"] == "cid-api"
    assert response.headers["x-correlation-id"] == "cid-api"
    assert response.headers["cache-control"] == "no-store"
    assert body["candidate_state"] == "NEW"
    assert body["duplicate_identity"] is False

    ids = {
        body["candidate_id"],
        body["offer_id"],
        body["product_id"],
        body["marketplace_product_id"],
    }
    assert len(ids) == 4

    got = client.get(f"/candidates/{body['candidate_id']}", headers={"X-Correlation-ID": "cid-get"})
    assert got.status_code == 200
    candidate = got.json()
    assert got.headers["x-correlation-id"] == "cid-get"
    assert candidate["candidate_id"] == body["candidate_id"]
    assert candidate["offer_id"] == body["offer_id"]
    assert candidate["product_id"] == body["product_id"]
    assert candidate["marketplace_product_id"] == body["marketplace_product_id"]
    assert candidate["raw_capture_id"] == body["raw_capture_id"]
    assert candidate["discovery_event_id"] == body["discovery_event_id"]
    assert candidate["audit_event_id"] == body["audit_event_id"]
    # The response preserves the capture-time correlation for tracing.
    assert candidate["correlation_id"] == "cid-api"


def test_repeated_capture_does_not_duplicate_identity(
    migrated_database_url: str, migrated_engine: Engine
) -> None:
    client = _client(migrated_database_url)
    first = client.post("/captures/manual", json=_payload()).json()
    second = client.post("/captures/manual", json=_payload()).json()

    assert second["marketplace_product_id"] == first["marketplace_product_id"]
    assert second["product_id"] == first["product_id"]
    assert second["candidate_id"] != first["candidate_id"]
    assert second["duplicate_identity"] is True
    assert _count(migrated_engine, "marketplace_product") == 1
    assert _count(migrated_engine, "product") == 1
    assert _count(migrated_engine, "offer") == 2


def test_sensitive_payload_is_rejected_without_writing(
    migrated_database_url: str, migrated_engine: Engine
) -> None:
    client = _client(migrated_database_url)
    payload = _payload()
    payload["password"] = "hunter2"
    response = client.post("/captures/manual", json=payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "RAD-CAP-002"
    assert error["retryable"] is False
    assert "password" in error["context"]["fields"]
    assert "hunter2" not in response.text

    nested = _payload()
    nested["offer"]["seller"] = {"name": "Loja", "token": "abc"}
    nested_response = client.post("/captures/manual", json=nested)
    assert nested_response.status_code == 422
    assert nested_response.json()["error"]["code"] == "RAD-CAP-002"

    url_token = _payload()
    url_token["product"]["url"] = "https://shopee.com.br/p/1?access_token=abc"
    url_response = client.post("/captures/manual", json=url_token)
    assert url_response.status_code == 422
    assert url_response.json()["error"]["code"] == "RAD-CAP-002"

    for table in _TABLES:
        assert _count(migrated_engine, table) == 0, table


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"marketplace": "AMAZON"}),
        lambda payload: payload["offer"].update({"current_price": 79.9}),
        lambda payload: payload["offer"].update({"current_price": "0"}),
        lambda payload: payload["product"].update({"url": "javascript:alert(1)"}),
        lambda payload: payload.update({"schema_version": "2.0"}),
    ],
)
def test_invalid_payload_returns_structured_error(migrated_database_url: str, mutate: Any) -> None:
    client = _client(migrated_database_url)
    payload = _payload()
    mutate(payload)
    response = client.post(
        "/captures/manual", json=payload, headers={"X-Correlation-ID": "cid-bad"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["correlation_id"] == "cid-bad"
    assert body["error"]["code"] == "RAD-CAP-001"
    assert body["error"]["retryable"] is False


def test_title_and_text_are_sanitized(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    payload = _payload()
    payload["product"]["title"] = "Cafeteira\n\n  12L \x00 "
    created = client.post("/captures/manual", json=payload).json()
    got = client.get(f"/candidates/{created['candidate_id']}").json()
    assert got["title"] == "Cafeteira 12L"


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.get("/candidates/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RAD-CAP-004"
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.post("/captures/manual", json=_payload())
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]


def test_extra_unknown_field_is_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    payload = _payload()
    payload["unexpected_field"] = "value"
    response = client.post("/captures/manual", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-CAP-001"
