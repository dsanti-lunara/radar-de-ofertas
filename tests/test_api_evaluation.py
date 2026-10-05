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
            "external_id": "MLB123",
            "title": "Produto",
            "url": "https://www.mercadolivre.com.br/p/MLB123",
            "category": "Perfumes",
        },
        "offer": {"current_price": "100.00", "sales_count": 2300, "seller": {"name": "Loja"}},
        "captured_at": "2026-10-05T12:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def _capture(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/captures/manual", json=_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _components(score: int) -> dict[str, int]:
    # Brand Fit is resolved from the active taxonomy, never supplied by the caller.
    return {
        "price_opportunity": score,
        "seller_quality": score,
        "demand": score,
    }


def _evaluate(
    client: TestClient,
    candidate_id: str,
    *,
    deal: dict[str, int],
    confidence: dict[str, int] | None = None,
    monetization: dict[str, int] | None = None,
    brand: str = "RADAR_BEAUTY",
    hard_rules: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "brand": brand,
        "deal": deal,
    }
    if confidence is not None:
        body["confidence"] = confidence
    if monetization is not None:
        body["monetization"] = monetization
    if hard_rules is not None:
        body["hard_rules"] = hard_rules
    response = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json=body,
        headers={"X-Correlation-ID": "cid-eval"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def _high_confidence() -> dict[str, int]:
    return {
        "source_reliability": 100,
        "freshness": 100,
        "completeness": 100,
        "price_history_depth": 100,
        "cross_validation": 100,
    }


def _medium_confidence() -> dict[str, int]:
    return {
        "source_reliability": 60,
        "freshness": 60,
        "completeness": 60,
        "price_history_depth": 60,
        "cross_validation": 60,
    }


def test_evaluation_returns_decision_and_is_queryable(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)

    body = _evaluate(
        client,
        captured["candidate_id"],
        deal=_components(100),
        confidence=_high_confidence(),
        monetization={
            "estimated_commission": 97,
            "effective_commission_percent": 97,
            "conversion_evidence": 97,
            "extra_commission": 97,
        },
    )

    assert body["status_code"] == 201
    assert body["schema_version"] == "1.0"
    assert body["status"] == "EVALUATED"
    assert body["correlation_id"] == "cid-eval"
    assert body["headers"]["x-correlation-id"] == "cid-eval"
    assert body["headers"]["cache-control"] == "no-store"
    assert body["candidate_id"] == captured["candidate_id"]
    assert body["brand"] == "RADAR_BEAUTY"
    assert body["deal_score"] == "100.00"
    assert body["monetization_score"] == 97
    assert body["confidence"] == "HIGH"
    assert body["decision"] == "APPROVE"
    assert body["auto_eligible"] is True
    assert body["failed_rules"] == []
    assert "INSUFFICIENT_REQUIRED_DATA" in body["passed_rules"]
    assert body["scoring_version"] == "evaluation-1.0"
    assert body["deal_scoring_version"] == "deal-1.0"
    assert body["monetization_scoring_version"] == "monetization-1.0"
    assert body["confidence_scoring_version"] == "confidence-1.0"
    assert body["taxonomy_version"] == APPROVED_TAXONOMY.taxonomy_version
    assert body["feature_snapshot"]["deal"]["brand_fit"] == 100
    assert body["breakdown"]["deal"]["score"] == "100.00"

    listing = client.get(f"/candidates/{captured['candidate_id']}/evaluations")
    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["status"] == "OK"
    assert listing_body["count"] == 1
    assert listing_body["evaluations"][0]["evaluation_id"] == body["evaluation_id"]
    assert listing_body["evaluations"][0]["decision"] == "APPROVE"


def test_boundaries_60_and_80_follow_the_matrix(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]
    # The approved taxonomy fixes Brand Fit = 100 for a Radar Beauty perfume
    # (weight 15), so these component triples land exactly on the boundaries.
    sixty = {"price_opportunity": 50, "seller_quality": 60, "demand": 50}
    seventy_nine = {"price_opportunity": 100, "seller_quality": 56, "demand": 50}
    eighty = {"price_opportunity": 100, "seller_quality": 60, "demand": 50}
    fifty_nine = {"price_opportunity": 50, "seller_quality": 56, "demand": 50}

    body = _evaluate(client, candidate_id, deal=sixty, confidence=_medium_confidence())
    assert body["deal_score"] == "60.00"
    assert body["decision"] == "REVIEW"

    body = _evaluate(client, candidate_id, deal=seventy_nine, confidence=_high_confidence())
    assert body["deal_score"] == "79.00"
    assert body["decision"] == "REVIEW"

    body = _evaluate(client, candidate_id, deal=eighty, confidence=_medium_confidence())
    assert body["deal_score"] == "80.00"
    assert body["decision"] == "APPROVE"

    body = _evaluate(client, candidate_id, deal=fifty_nine, confidence=_high_confidence())
    assert body["deal_score"] == "59.00"
    assert body["decision"] == "REJECT"


def test_missing_required_data_is_blocking_and_persisted(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _evaluate(
        client,
        candidate_id,
        deal={"price_opportunity": 100, "demand": 100},
        confidence=_high_confidence(),
    )

    assert body["status_code"] == 201
    assert body["deal_score"] is None
    assert body["deal_score"] != "0.00"
    assert body["decision"] == "REJECT"
    assert "INSUFFICIENT_REQUIRED_DATA" in [rule["rule"] for rule in body["failed_rules"]]
    assert any(warning["code"] == "DEAL_COMPONENT_MISSING" for warning in body["warnings"])


def test_hard_rules_reject_before_ai_link_and_publication(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    # The Candidate is a Radar Beauty perfume, so CASA_EM_ORDEM classifies it out
    # of scope: the Hard Rule must reject even with a perfect Deal/Confidence.
    body = _evaluate(
        client,
        candidate_id,
        deal=_components(100),
        confidence=_high_confidence(),
        brand="CASA_EM_ORDEM",
    )

    assert body["decision"] == "REJECT"
    assert body["auto_eligible"] is False
    assert "OUT_OF_SCOPE_CATEGORY" in [rule["rule"] for rule in body["failed_rules"]]
    # No AI review, affiliate link or Opportunity is created by the Evaluation.
    assert "affiliate_link" not in body
    assert "ai_review" not in body
    assert "opportunity_id" not in body


def test_declared_hard_rule_rejects(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _evaluate(
        client,
        candidate_id,
        deal=_components(100),
        confidence=_high_confidence(),
        hard_rules=["COMPLIANCE_BLOCK"],
    )

    assert body["decision"] == "REJECT"
    assert "COMPLIANCE_BLOCK" in [rule["rule"] for rule in body["failed_rules"]]


def test_deal_45_with_monetization_97_stays_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _evaluate(
        client,
        candidate_id,
        deal={"price_opportunity": 30, "seller_quality": 40, "demand": 40},
        confidence=_high_confidence(),
        monetization={
            "estimated_commission": 97,
            "effective_commission_percent": 97,
            "conversion_evidence": 97,
            "extra_commission": 97,
        },
    )

    assert body["deal_score"] == "45.00"
    assert body["monetization_score"] == 97
    assert body["decision"] == "REJECT"


def test_commission_does_not_change_the_deal_score(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    deal = {"price_opportunity": 100, "seller_quality": 100, "demand": 25}
    low = _evaluate(
        client,
        candidate_id,
        deal=deal,
        confidence=_high_confidence(),
        monetization={"estimated_commission": 0, "conversion_evidence": 0},
    )
    high = _evaluate(
        client,
        candidate_id,
        deal=deal,
        confidence=_high_confidence(),
        monetization={
            "estimated_commission": 100,
            "effective_commission_percent": 100,
            "conversion_evidence": 100,
            "extra_commission": 100,
        },
    )

    assert low["deal_score"] == high["deal_score"] == "85.00"
    assert low["decision"] == high["decision"] == "APPROVE"


def test_evaluations_are_immutable_and_traceable_via_public_boundary(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    first = _evaluate(client, candidate_id, deal=_components(85), confidence=_high_confidence())
    second = _evaluate(client, candidate_id, deal=_components(45), confidence=_high_confidence())

    assert first["evaluation_id"] != second["evaluation_id"]
    listing = client.get(f"/candidates/{candidate_id}/evaluations").json()
    assert listing["count"] == 2
    assert [item["evaluation_id"] for item in listing["evaluations"]] == [
        first["evaluation_id"],
        second["evaluation_id"],
    ]
    # The first evaluation is preserved exactly as it was written.
    assert listing["evaluations"][0]["deal_score"] == first["deal_score"]
    assert listing["evaluations"][0]["decision"] == first["decision"]
    assert listing["evaluations"][0]["breakdown"]["deal"]["scoring_version"] == "deal-1.0"


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    body = _evaluate(client, "cand_missing", deal=_components(100))

    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-004"

    listing = client.get("/candidates/cand_missing/evaluations")
    assert listing.status_code == 404
    assert listing.json()["error"]["code"] == "RAD-CAP-004"


def test_invalid_component_score_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _evaluate(
        client,
        candidate_id,
        deal={"price_opportunity": 101, "seller_quality": 100, "demand": 100},
    )

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-011"
    assert body["error"]["retryable"] is False


def test_unknown_hard_rule_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _evaluate(
        client,
        candidate_id,
        deal=_components(100),
        hard_rules=["NOT_A_REAL_RULE"],
    )

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-011"
    assert body["error"]["context"]["hard_rule"] == "NOT_A_REAL_RULE"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    response = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json={"schema_version": "1.0", "brand": "RADAR_BEAUTY", "deal": _components(85)},
    )
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
