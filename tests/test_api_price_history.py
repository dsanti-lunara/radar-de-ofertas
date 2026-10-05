from __future__ import annotations

from typing import Any

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


def test_price_history_returns_series_with_provenance(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    first = client.post(
        "/captures/manual",
        json=_payload(captured_at="2026-10-05T12:00:00+00:00"),
        headers={"X-Correlation-ID": "cid-1"},
    ).json()
    second_payload = _payload(captured_at="2026-10-05T18:00:00+00:00")
    second_payload["offer"]["current_price"] = "69.90"
    client.post("/captures/manual", json=second_payload, headers={"X-Correlation-ID": "cid-2"})

    assert first["price_observation_id"]

    response = client.get(
        f"/marketplace-products/{first['marketplace_product_id']}/price-history",
        headers={"X-Correlation-ID": "cid-history"},
    )
    assert response.status_code == 200
    assert response.headers["x-correlation-id"] == "cid-history"
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "OK"
    assert body["correlation_id"] == "cid-history"
    assert body["marketplace_product_id"] == first["marketplace_product_id"]
    assert body["marketplace"] == "MERCADO_LIVRE"
    assert body["external_id"] == "MLB123"
    assert body["observation_count"] == 2

    observations = body["observations"]
    assert [point["price"] for point in observations] == ["79.90", "69.90"]
    assert [point["observed_at"] for point in observations] == [
        "2026-10-05T12:00:00+00:00",
        "2026-10-05T18:00:00+00:00",
    ]
    assert observations[0]["correlation_id"] == "cid-1"
    assert observations[0]["source"] == "BROWSER_EXTENSION"
    assert observations[0]["raw_capture_id"] == first["raw_capture_id"]
    assert observations[0]["price_observation_id"] == first["price_observation_id"]


def test_repeated_identical_capture_keeps_single_observation(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    first = client.post("/captures/manual", json=_payload()).json()
    repeated = client.post("/captures/manual", json=_payload()).json()

    assert repeated["price_observation_id"] == first["price_observation_id"]

    response = client.get(f"/marketplace-products/{first['marketplace_product_id']}/price-history")
    body = response.json()
    assert body["observation_count"] == 1
    assert body["observations"][0]["price"] == "79.90"


def test_unknown_marketplace_product_returns_structured_404(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    response = client.get("/marketplace-products/does-not-exist/price-history")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RAD-CAP-005"
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
