from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.seller_quality import (
    APPROVED_SELLER_QUALITY_NORMALIZATION,
    WARNING_CONTRADICTION,
    WARNING_INVALID_DATA,
    WARNING_MISSING_DATA,
    WARNING_NORMALIZATION_NOT_DEFINED,
    SellerQualityComponentName,
    SellerQualityNormalization,
    build_seller_quality_normalization,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _normalization() -> SellerQualityNormalization:
    return build_seller_quality_normalization(
        {
            "schema_version": "1.0",
            "normalization_version": "seller-quality-normalization-test",
            "marketplace_reputation": {"gold": 100, "green": 80},
            "rating": [
                {"min": "4.5", "max": "5.0", "score": 100},
                {"min": "0", "max": "4.4999", "score": 50},
            ],
            "sales_history": [
                {"min": 1000, "max": None, "score": 100},
                {"min": 0, "max": 999, "score": 50},
            ],
            "trusted_status": {"true": 100, "false": 0},
        }
    )


def _client(
    database_url: str,
    normalization: SellerQualityNormalization | None = None,
) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            seller_quality=normalization or _normalization(),
        )
    )


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
        f"/candidates/{candidate_id}/seller-quality",
        params=params,
        headers={"X-Correlation-ID": "cid-seller"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def _component(body: dict[str, Any], name: SellerQualityComponentName) -> dict[str, Any]:
    return next(item for item in body["components"] if item["name"] == name.value)


def test_seller_quality_returns_breakdown_with_provenance(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _evaluate(
        client,
        captured["candidate_id"],
        reputation="gold",
        rating="4.6",
        trusted="true",
    )

    assert body["status_code"] == 200
    assert body["schema_version"] == "1.0"
    assert body["status"] == "EVALUATED"
    assert body["correlation_id"] == "cid-seller"
    assert body["headers"]["x-correlation-id"] == "cid-seller"
    assert body["headers"]["cache-control"] == "no-store"
    assert body["seller"] == {"id": None, "name": "Loja"}
    assert body["seller_quality"] == 100
    assert body["fully_calibrated"] is True
    assert body["weight_covered"] == 100
    assert body["scoring_version"] == "seller-quality-1.0"
    assert body["normalization_version"] == "seller-quality-normalization-test"

    reputation = _component(body, SellerQualityComponentName.MARKETPLACE_REPUTATION)
    assert reputation["score"] == 100
    assert reputation["source"] == "evaluation_input"
    assert reputation["raw"] == "gold"

    sales = _component(body, SellerQualityComponentName.SALES_HISTORY)
    assert sales["score"] == 100
    assert sales["source"] == "persisted_offer"
    assert sales["raw"] == 2300

    assert body["warnings"] == []


def test_default_baseline_reports_gaps_without_inventing_values(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, normalization=APPROVED_SELLER_QUALITY_NORMALIZATION)
    captured = _capture(client)

    body = _evaluate(client, captured["candidate_id"])

    assert body["status_code"] == 200
    assert body["seller_quality"] is None
    assert body["weight_covered"] == 0
    assert body["fully_calibrated"] is False
    # Persisted sales_count is present but has no configured normalization.
    assert _component(body, SellerQualityComponentName.SALES_HISTORY)["reason"] == (
        "normalization_not_defined"
    )
    assert _component(body, SellerQualityComponentName.RATING)["reason"] == "missing_data"
    codes = [warning["code"] for warning in body["warnings"]]
    assert WARNING_NORMALIZATION_NOT_DEFINED in codes
    assert WARNING_MISSING_DATA in codes


def test_missing_signals_do_not_become_zero(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(
        client,
        offer={"current_price": "100.00", "seller": {"name": "Loja"}},
    )

    body = _evaluate(client, captured["candidate_id"])

    rating = _component(body, SellerQualityComponentName.RATING)
    assert rating["score"] is None
    assert rating["score"] != 0
    assert rating["reason"] == "missing_data"
    assert body["seller_quality"] is None
    assert body["seller_quality"] != 0
    assert body["weight_covered"] == 0


def test_invalid_rating_generates_warning(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _evaluate(client, captured["candidate_id"], rating="-1.0")

    rating = _component(body, SellerQualityComponentName.RATING)
    assert body["status_code"] == 200
    assert rating["score"] is None
    assert rating["reason"] == "invalid_data"
    assert WARNING_INVALID_DATA in [warning["code"] for warning in body["warnings"]]


def test_contradictory_signals_without_identity_generate_warning(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    offer = {"current_price": "100.00", "sales_count": 2300}
    captured = _capture(client, offer=offer)

    body = _evaluate(client, captured["candidate_id"], trusted="true")

    assert body["status_code"] == 200
    assert body["seller"] == {"id": None, "name": None}
    assert WARNING_CONTRADICTION in [warning["code"] for warning in body["warnings"]]


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    body = _evaluate(client, "cand_missing")

    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-004"
    assert body["headers"]["x-correlation-id"] == body["correlation_id"]


def test_malformed_rating_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _evaluate(client, captured["candidate_id"], rating="not-a-number")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-009"
    assert body["error"]["retryable"] is False
    assert body["error"]["context"]["field"] == "rating"


def test_malformed_trusted_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _evaluate(client, captured["candidate_id"], trusted="maybe")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-009"
    assert body["error"]["context"]["field"] == "trusted"


def test_malformed_sales_count_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _evaluate(client, captured["candidate_id"], sales_count="1.5")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-009"
    assert body["error"]["context"]["field"] == "sales_count"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    response = client.get(f"/candidates/{captured['candidate_id']}/seller-quality")
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
