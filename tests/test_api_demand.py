from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.demand import (
    APPROVED_DEMAND_NORMALIZATION,
    WARNING_MISSING_DATA,
    WARNING_NORMALIZATION_NOT_DEFINED,
    DemandNormalization,
    DemandSignalName,
    build_demand_normalization,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _normalization() -> DemandNormalization:
    return build_demand_normalization(
        {
            "schema_version": "1.0",
            "normalization_version": "demand-normalization-test",
            "categories": {
                "perfume": {
                    "weights": {
                        "sales_count": 40,
                        "rating_count": 20,
                        "trend": 20,
                        "affiliate_portal": 10,
                        "badges": 10,
                    },
                    "sales_count": [
                        {"min": 1000, "max": None, "score": 100},
                        {"min": 0, "max": 999, "score": 50},
                    ],
                    "rating_count": [
                        {"min": 500, "max": None, "score": 100},
                        {"min": 0, "max": 499, "score": 50},
                    ],
                    "trend": {"rising": 100, "stable": 60},
                    "affiliate_portal": {"featured": 100, "listed": 60},
                    "badges": {"best seller": 100, "free shipping": 70},
                }
            },
        }
    )


def _incomplete_normalization() -> DemandNormalization:
    return build_demand_normalization(
        {
            "schema_version": "1.0",
            "normalization_version": "demand-normalization-incomplete",
            "categories": {
                "perfume": {
                    "weights": {
                        "sales_count": 40,
                        "rating_count": 20,
                        "trend": 20,
                        "affiliate_portal": 10,
                    },
                    "sales_count": [{"min": 1000, "max": None, "score": 100}],
                    "rating_count": [{"min": 500, "max": None, "score": 100}],
                    "trend": {"rising": 100},
                    "affiliate_portal": {"featured": 100},
                }
            },
        }
    )


def _client(
    database_url: str,
    normalization: DemandNormalization | None = None,
) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            demand=normalization or _normalization(),
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
            "category": "Perfumes",
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
        f"/candidates/{candidate_id}/demand",
        params=params,
        headers={"X-Correlation-ID": "cid-demand"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def _component(body: dict[str, Any], name: DemandSignalName) -> dict[str, Any]:
    return next(item for item in body["components"] if item["name"] == name.value)


def test_demand_returns_breakdown_with_provenance(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _evaluate(
        client,
        captured["candidate_id"],
        rating_count="600",
        trend="rising",
        affiliate_portal="featured",
        badges="best seller",
    )

    assert body["status_code"] == 200
    assert body["schema_version"] == "1.0"
    assert body["status"] == "EVALUATED"
    assert body["correlation_id"] == "cid-demand"
    assert body["headers"]["x-correlation-id"] == "cid-demand"
    assert body["headers"]["cache-control"] == "no-store"
    assert body["raw_category"] == "Perfumes"
    assert body["category"] == "perfume"
    assert body["demand"] == 100
    assert body["fully_calibrated"] is True
    assert body["weight_covered"] == 100
    assert body["scoring_version"] == "demand-1.0"
    assert body["normalization_version"] == "demand-normalization-test"

    sales = _component(body, DemandSignalName.SALES_COUNT)
    assert sales["score"] == 100
    assert sales["source"] == "persisted_offer"
    assert sales["raw"] == 2300

    trend = _component(body, DemandSignalName.TREND)
    assert trend["score"] == 100
    assert trend["source"] == "evaluation_input"
    assert trend["raw"] == "rising"

    badges = _component(body, DemandSignalName.BADGES)
    assert badges["raw"] == ["best seller"]

    assert body["warnings"] == []


def test_default_baseline_reports_gaps_without_inventing_values(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, normalization=APPROVED_DEMAND_NORMALIZATION)
    captured = _capture(client)

    body = _evaluate(client, captured["candidate_id"])

    assert body["status_code"] == 200
    assert body["demand"] is None
    assert body["demand"] != 0
    assert body["weight_covered"] == 0
    assert body["fully_calibrated"] is False
    # Persisted sales_count is present but the category has no configuration.
    assert _component(body, DemandSignalName.SALES_COUNT)["reason"] == ("normalization_not_defined")
    assert _component(body, DemandSignalName.TREND)["reason"] == "missing_data"
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

    trend = _component(body, DemandSignalName.TREND)
    assert trend["score"] is None
    assert trend["score"] != 0
    assert trend["reason"] == "missing_data"
    assert _component(body, DemandSignalName.SALES_COUNT)["reason"] == "missing_data"
    assert body["demand"] is None
    assert body["demand"] != 0
    assert body["weight_covered"] == 0
    assert body["fully_calibrated"] is False


def test_incomplete_configuration_is_not_presented_as_validated(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, normalization=_incomplete_normalization())
    captured = _capture(client)

    body = _evaluate(
        client,
        captured["candidate_id"],
        rating_count="600",
        trend="rising",
        affiliate_portal="featured",
        badges="best seller",
    )

    assert body["status_code"] == 200
    # Every signal carries data, but the category config omits the badges
    # mapping/weight, so the result must not be presented as validated.
    assert body["fully_calibrated"] is False
    badges = _component(body, DemandSignalName.BADGES)
    assert badges["calibrated"] is False
    assert badges["weight"] is None
    assert badges["reason"] == "normalization_not_defined"
    assert WARNING_NORMALIZATION_NOT_DEFINED in [warning["code"] for warning in body["warnings"]]


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    body = _evaluate(client, "cand_missing")

    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-004"
    assert body["headers"]["x-correlation-id"] == body["correlation_id"]


def test_malformed_rating_count_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _evaluate(client, captured["candidate_id"], rating_count="1.5")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-010"
    assert body["error"]["retryable"] is False
    assert body["error"]["context"]["field"] == "rating_count"


def test_empty_badges_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _evaluate(client, captured["candidate_id"], badges=",")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-010"
    assert body["error"]["context"]["field"] == "badges"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    response = client.get(f"/candidates/{captured['candidate_id']}/demand")
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
