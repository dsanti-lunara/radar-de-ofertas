from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
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
            "external_id": "MLB-CLAIM",
            "title": "Perfume",
            "url": "https://www.mercadolivre.com.br/p/MLB-CLAIM",
            "category": "Perfumes",
        },
        "offer": {"current_price": "100.00", "sales_count": 2300, "seller": {"name": "Loja"}},
        "captured_at": "2026-09-01T12:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def _capture(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/captures/manual", json=_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _evaluate(client: TestClient, candidate_id: str) -> dict[str, Any]:
    body = {
        "schema_version": "1.0",
        "brand": "RADAR_BEAUTY",
        "deal": {"price_opportunity": 85, "seller_quality": 85, "demand": 85},
        "confidence": {
            "source_reliability": 90,
            "freshness": 90,
            "completeness": 90,
            "price_history_depth": 90,
            "cross_validation": 90,
        },
    }
    response = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json=body,
        headers={"X-Correlation-ID": "cid-eval"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _claims(client: TestClient, candidate_id: str, **params: Any) -> dict[str, Any]:
    response = client.get(
        f"/candidates/{candidate_id}/allowed-claims",
        params=params,
        headers={"X-Correlation-ID": "cid-claims"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def _by_type(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {claim["claim_type"]: claim for claim in body["claims"]}


def test_current_and_history_claims_are_traceable_via_public_boundary(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    first = _capture(client, offer={"current_price": "100.00", "sales_count": 2300})
    second = _capture(
        client,
        offer={"current_price": "80.00", "sales_count": 2300},
        captured_at="2026-09-20T12:00:00+00:00",
    )
    evaluation = _evaluate(client, second["candidate_id"])

    body = _claims(client, second["candidate_id"])

    assert body["status_code"] == 200
    assert body["schema_version"] == "1.0"
    assert body["status"] == "OK"
    assert body["engine_version"] == "allowed-claims-1.0"
    assert body["correlation_id"] == "cid-claims"
    assert body["headers"]["x-correlation-id"] == "cid-claims"
    assert body["headers"]["cache-control"] == "no-store"
    assert body["evaluation_id"] == evaluation["evaluation_id"]
    assert body["evaluation_decision"] == evaluation["decision"]
    assert body["claim_count"] == len(body["claims"])

    claims = _by_type(body)
    assert claims["CURRENT_PRICE"]["value"] == "80.00"
    assert claims["CURRENT_PRICE"]["unit"] == "money"
    assert claims["PREVIOUS_OBSERVED_PRICE"]["value"] == "100.00"
    assert claims["PRICE_DROP_PERCENT"]["value"] == "20.00"
    assert claims["SALES_COUNT"]["value"] == "2300"

    # Provenance points back to the exact RawCapture of each public capture.
    current_evidence = claims["CURRENT_PRICE"]["evidence"][0]
    assert current_evidence["evidence_type"] == "offer"
    assert current_evidence["reference_id"] == second["offer_id"]
    assert current_evidence["raw_capture_id"] == second["raw_capture_id"]

    previous_evidence = claims["PREVIOUS_OBSERVED_PRICE"]["evidence"][0]
    assert previous_evidence["evidence_type"] == "price_observation"
    assert previous_evidence["raw_capture_id"] == first["raw_capture_id"]
    assert previous_evidence["correlation_id"] == first["correlation_id"]


def test_lowest_observed_30d_is_omitted_without_covered_history(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    captured = _capture(
        client,
        offer={"current_price": "80.00"},
        captured_at="2026-09-20T12:00:00+00:00",
    )
    _evaluate(client, captured["candidate_id"])

    body = _claims(client, captured["candidate_id"])

    assert "LOWEST_OBSERVED_30D" not in _by_type(body)
    omitted = {item["claim_type"]: item["reason_code"] for item in body["omitted_claims"]}
    assert omitted["LOWEST_OBSERVED_30D"] == "HISTORY_INSUFFICIENT"
    assert any(
        warning["code"] == "LOWEST_OBSERVED_30D_HISTORY_INSUFFICIENT"
        for warning in body["warnings"]
    )


def test_lowest_observed_30d_is_produced_with_covered_history(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    _capture(
        client,
        offer={"current_price": "120.00"},
        captured_at="2026-08-01T12:00:00+00:00",
    )
    second = _capture(
        client,
        offer={"current_price": "80.00"},
        captured_at="2026-09-20T12:00:00+00:00",
    )
    _evaluate(client, second["candidate_id"])

    body = _claims(client, second["candidate_id"])

    claim = _by_type(body)["LOWEST_OBSERVED_30D"]
    assert claim["value"] == "80.00"
    assert any(item["field"] == "coverage" for item in claim["evidence"])


def test_coupon_state_controls_the_confirmed_coupon_claim(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    _evaluate(client, captured["candidate_id"])

    likely = _claims(client, captured["candidate_id"], coupon_state="LIKELY", coupon_amount="10")
    assert "CONFIRMED_COUPON" not in _by_type(likely)
    omitted = {item["claim_type"]: item["reason_code"] for item in likely["omitted_claims"]}
    assert omitted["CONFIRMED_COUPON"] == "COUPON_NOT_CONFIRMED"

    confirmed = _claims(
        client,
        captured["candidate_id"],
        coupon_state="CONFIRMED",
        coupon_amount="10",
        coupon_code="RADAR10",
    )
    assert _by_type(confirmed)["CONFIRMED_COUPON"]["value"] == "RADAR10"


def test_struck_through_price_does_not_become_proof(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(
        client,
        offer={"current_price": "80.00", "original_price": "199.00"},
        captured_at="2026-09-20T12:00:00+00:00",
    )
    _evaluate(client, captured["candidate_id"])

    body = _claims(client, captured["candidate_id"])

    claims = _by_type(body)
    assert "PREVIOUS_OBSERVED_PRICE" not in claims
    assert "PRICE_DROP_PERCENT" not in claims
    assert any(warning["code"] == "STRUCK_THROUGH_PRICE_NOT_PROOF" for warning in body["warnings"])


def test_forbidden_claims_are_explicit_and_never_produced(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    _evaluate(client, captured["candidate_id"])

    body = _claims(client, captured["candidate_id"])

    assert "UNVERIFIED_COUPON" in body["forbidden_claims"]
    assert "BEST_PRICE_ON_THE_INTERNET" in body["forbidden_claims"]
    produced = set(_by_type(body))
    assert produced.isdisjoint(body["forbidden_claims"])


def test_evaluation_version_can_be_selected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    first = _evaluate(client, captured["candidate_id"])
    _evaluate(client, captured["candidate_id"])

    body = _claims(client, captured["candidate_id"], evaluation_id=first["evaluation_id"])

    assert body["evaluation_id"] == first["evaluation_id"]


def test_candidate_without_evaluation_fails_closed(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _claims(client, captured["candidate_id"])

    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-013"
    assert body["error"]["retryable"] is False


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    body = _claims(client, "cand_missing")

    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-004"


def test_invalid_coupon_state_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    _evaluate(client, captured["candidate_id"])

    body = _claims(client, captured["candidate_id"], coupon_state="INVALID")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-014"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    _evaluate(client, captured["candidate_id"])

    response = client.get(f"/candidates/{captured['candidate_id']}/allowed-claims")
    body = response.json()

    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
