from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.price_opportunity import (
    WARNING_CALIBRATION_REQUIRED,
    WARNING_COUPON_NOT_CONFIRMED,
    WARNING_NO_MARKETPLACE_REFERENCE,
    WARNING_NO_PRICE_REFERENCE,
    WARNING_SHORT_PRICE_HISTORY,
    WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF,
    WARNING_UNKNOWN_SHIPPING,
    PriceOpportunityComponentName,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _client(database_url: str) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(create_app(settings=settings, engine=engine, taxonomy=APPROVED_TAXONOMY))


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
            "current_price": "100.00",
            "original_price": "150.00",
            "sales_count": 2300,
            "seller": {"name": "Loja"},
        },
        "captured_at": "2026-10-05T12:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def _capture(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/captures/manual", json=_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _evaluate(client: TestClient, candidate_id: str, **params: str) -> dict[str, Any]:
    response = client.get(
        f"/candidates/{candidate_id}/price-opportunity",
        params=params,
        headers={"X-Correlation-ID": "cid-price"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def _component(body: dict[str, Any], name: PriceOpportunityComponentName) -> dict[str, Any]:
    return next(item for item in body["components"] if item["name"] == name.value)


def test_price_opportunity_returns_breakdown_with_provenance(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    _capture(
        client,
        captured_at="2026-10-05T12:00:00+00:00",
        offer={**_payload()["offer"], "current_price": "100.00"},
    )
    second = _capture(
        client,
        captured_at="2026-10-05T18:00:00+00:00",
        offer={**_payload()["offer"], "current_price": "80.00"},
    )

    body = _evaluate(client, second["candidate_id"])

    assert body["status_code"] == 200
    assert body["schema_version"] == "1.0"
    assert body["status"] == "EVALUATED"
    assert body["correlation_id"] == "cid-price"
    assert body["headers"]["x-correlation-id"] == "cid-price"
    assert body["headers"]["cache-control"] == "no-store"
    assert body["candidate_id"] == second["candidate_id"]
    assert body["current_price"] == "80.00"
    assert body["history"]["observation_count"] == 2
    assert body["history"]["prior_observation_count"] == 1
    assert body["history"]["source"] == "30d"

    assert _component(body, PriceOpportunityComponentName.HISTORICAL_POSITION)["score"] == 100
    assert _component(body, PriceOpportunityComponentName.RECENT_PRICE_DROP)["score"] == 90
    assert _component(body, PriceOpportunityComponentName.MARKETPLACE_COMPARISON)["score"] == 50
    assert body["price_opportunity"] == 86
    assert body["fully_calibrated"] is False

    codes = [warning["code"] for warning in body["warnings"]]
    assert WARNING_NO_MARKETPLACE_REFERENCE in codes
    assert WARNING_UNKNOWN_SHIPPING in codes
    assert WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF in codes
    assert WARNING_CALIBRATION_REQUIRED in codes


def test_insufficient_history_uses_neutral_50(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _evaluate(client, captured["candidate_id"])

    assert body["status_code"] == 200
    assert body["history"]["prior_observation_count"] == 0
    assert body["history"]["source"] == "none"
    assert _component(body, PriceOpportunityComponentName.HISTORICAL_POSITION)["score"] == 50
    assert _component(body, PriceOpportunityComponentName.RECENT_PRICE_DROP)["score"] == 50
    assert body["price_opportunity"] == 50
    codes = [warning["code"] for warning in body["warnings"]]
    assert WARNING_SHORT_PRICE_HISTORY in codes
    assert WARNING_NO_PRICE_REFERENCE in codes


def test_unconfirmed_coupon_does_not_reduce_effective_price(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _evaluate(
        client,
        captured["candidate_id"],
        shipping_cost="0.00",
        coupon_state="LIKELY",
        coupon_amount="20.00",
        coupon_code="TALVEZ",
    )

    assert body["status_code"] == 200
    assert body["effective_price"] == "100.00"
    assert body["coupon"]["state"] == "LIKELY"
    assert body["coupon"]["applied"] is False
    assert WARNING_COUPON_NOT_CONFIRMED in [warning["code"] for warning in body["warnings"]]


def test_confirmed_coupon_reduces_effective_price(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _evaluate(
        client,
        captured["candidate_id"],
        shipping_cost="5.00",
        coupon_state="CONFIRMED",
        coupon_amount="20.00",
    )

    assert body["status_code"] == 200
    assert body["effective_price"] == "85.00"
    assert body["coupon"]["applied"] is True
    assert WARNING_COUPON_NOT_CONFIRMED not in [warning["code"] for warning in body["warnings"]]


def test_unknown_shipping_is_explicit(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _evaluate(client, captured["candidate_id"])

    assert body["shipping_known"] is False
    assert body["effective_price"] is None
    assert WARNING_UNKNOWN_SHIPPING in [warning["code"] for warning in body["warnings"]]


def test_comparable_reference_is_used(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _evaluate(
        client,
        captured["candidate_id"],
        shipping_cost="0.00",
        comparable_price="100.00",
        comparable_marketplace="SHOPEE",
    )

    assert body["status_code"] == 200
    comparison = _component(body, PriceOpportunityComponentName.MARKETPLACE_COMPARISON)
    assert comparison["score"] == 100
    assert comparison["detail"]["comparable_marketplace"] == "SHOPEE"
    assert WARNING_NO_MARKETPLACE_REFERENCE not in [w["code"] for w in body["warnings"]]


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    body = _evaluate(client, "cand_missing")

    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-004"
    assert body["headers"]["x-correlation-id"] == body["correlation_id"]


def test_invalid_coupon_state_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _evaluate(client, captured["candidate_id"], coupon_state="MAYBE")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-008"
    assert body["error"]["retryable"] is False
    assert body["error"]["context"]["field"] == "coupon_state"


def test_invalid_shipping_cost_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _evaluate(client, captured["candidate_id"], shipping_cost="not-money")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-008"
    assert body["error"]["context"]["field"] == "shipping_cost"


def test_non_positive_comparable_price_returns_structured_422(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _evaluate(client, captured["candidate_id"], comparable_price="0")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-008"
    assert body["error"]["context"]["field"] == "comparable_price"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    response = client.get(f"/candidates/{captured['candidate_id']}/price-opportunity")
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
