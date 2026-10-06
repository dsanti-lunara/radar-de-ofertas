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


def _capture_payload(title: str = "Perfume") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "marketplace": "MERCADO_LIVRE",
        "source": "BROWSER_EXTENSION",
        "product": {
            "external_id": "MLB-REVIEW",
            "title": title,
            "url": "https://www.mercadolivre.com.br/p/MLB-REVIEW",
            "category": "Perfumes",
        },
        "offer": {"current_price": "80.00", "sales_count": 2300, "seller": {"name": "Loja"}},
        "captured_at": "2026-10-06T12:00:00+00:00",
    }


def _capture(client: TestClient, *, title: str = "Perfume") -> str:
    response = client.post("/captures/manual", json=_capture_payload(title))
    assert response.status_code == 201, response.text
    return response.json()["candidate_id"]


def _evaluate(client: TestClient, candidate_id: str, *, score: int = 100) -> None:
    response = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json={
            "schema_version": "1.0",
            "brand": "RADAR_BEAUTY",
            "deal": {
                "price_opportunity": score,
                "seller_quality": score,
                "demand": score,
            },
            "confidence": {
                "source_reliability": score,
                "freshness": score,
                "completeness": score,
                "price_history_depth": score,
                "cross_validation": score,
            },
        },
        headers={"X-Correlation-ID": "cid-eval"},
    )
    assert response.status_code == 201, response.text


def _ai_review(client: TestClient, candidate_id: str) -> dict[str, Any]:
    response = client.post(
        f"/candidates/{candidate_id}/ai-review",
        json={"schema_version": "1.0", "channel": "TELEGRAM"},
        headers={"X-Correlation-ID": "cid-ai"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _reviewed_candidate(client: TestClient) -> tuple[str, dict[str, Any]]:
    candidate_id = _capture(client)
    _evaluate(client, candidate_id)
    ai_review = _ai_review(client, candidate_id)
    return candidate_id, ai_review


def _post_review(client: TestClient, candidate_id: str, **body: Any) -> Any:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "human_decision": "APPROVE",
        "reason": "Preço confere com a evidência",
    }
    payload.update(body)
    return client.post(
        f"/candidates/{candidate_id}/human-reviews",
        json=payload,
        headers={"X-Correlation-ID": "cid-review"},
    )


def test_inbox_and_detail_use_real_data_with_timeline_and_versions(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id, _ = _reviewed_candidate(client)

    inbox = client.get("/review/inbox")
    assert inbox.status_code == 200
    body = inbox.json()
    assert body["schema_version"] == "1.0"
    assert body["correlation_id"]
    assert body["count"] == 1
    item = body["items"][0]
    assert item["candidate_id"] == candidate_id
    assert item["marketplace"] == "MERCADO_LIVRE"
    assert item["current_price"] == "80.00"
    assert item["deal_score"] == "100.00"
    assert item["decision"] == "APPROVE"
    assert item["ai_decision"] == "APPROVE"
    assert item["opportunity_id"] is None

    detail = client.get(f"/review/candidates/{candidate_id}")
    assert detail.status_code == 200
    detail_body = detail.json()["detail"]
    assert detail_body["evaluation"]["decision"] == "APPROVE"
    assert detail_body["price_history"]
    assert detail_body["evidence"]
    assert detail_body["ai_reviews"][0]["decision"] == "APPROVE"
    assert detail_body["versions"]["scoring_version"]
    assert detail_body["versions"]["ai_knowledge_version"]
    timeline = [entry["event_type"] for entry in detail_body["timeline"]]
    assert "CAPTURE_RECEIVED" in timeline
    assert "EVALUATION_RECORDED" in timeline
    assert "AI_REVIEW_RECORDED" in timeline


def test_review_preserves_the_ai_and_human_decision_and_reason(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id, ai_review = _reviewed_candidate(client)

    response = _post_review(
        client,
        candidate_id,
        human_decision="REJECT",
        reason="Preço mudou depois da avaliação",
        ai_review_id=ai_review["ai_review_id"],
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "RECORDED"
    assert body["correlation_id"] == "cid-review"
    review = body["human_review"]
    assert review["ai_decision"] == "APPROVE"
    assert review["human_decision"] == "REJECT"
    assert review["reason"] == "Preço mudou depois da avaliação"
    assert review["decision_matches_ai"] is False
    assert review["publication_authorized"] is False
    assert response.headers["x-correlation-id"] == "cid-review"
    assert response.headers["cache-control"] == "no-store"

    listing = client.get(f"/candidates/{candidate_id}/human-reviews")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1

    by_id = client.get(f"/human-reviews/{review['human_review_id']}")
    assert by_id.status_code == 200
    assert by_id.json()["human_review"]["human_decision"] == "REJECT"

    # The decision is now part of the Candidate timeline.
    timeline = client.get(f"/review/candidates/{candidate_id}").json()["detail"]["timeline"]
    assert any(entry["event_type"] == "HUMAN_REVIEW_RECORDED" for entry in timeline)


def test_edit_content_requires_the_payload_and_persists_the_snapshot(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id, _ = _reviewed_candidate(client)

    missing = _post_review(
        client, candidate_id, human_decision="EDIT_CONTENT", reason="Ajustar CTA"
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "RAD-UI-001"
    assert client.get(f"/candidates/{candidate_id}/human-reviews").json()["count"] == 0

    response = _post_review(
        client,
        candidate_id,
        human_decision="EDIT_CONTENT",
        reason="Ajustar CTA",
        edited_content={"headline": "Oferta", "body": "Corpo", "cta": "Comprar <b>agora</b>"},
    )
    assert response.status_code == 201, response.text
    edited = response.json()["human_review"]["edited_content"]
    assert edited == {"headline": "Oferta", "body": "Corpo", "cta": "Comprar agora"}


def test_candidate_approval_does_not_authorize_publication(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id, _ = _reviewed_candidate(client)

    response = _post_review(client, candidate_id, human_decision="APPROVE", reason="ok")
    assert response.status_code == 201

    body = response.json()
    assert body["publication_authorized"] is False
    assert body["automation"]["publish_allowed"] is False
    assert body["note"]

    engine = create_database_engine(migrated_database_url)
    try:
        with engine.connect() as connection:
            publications = connection.exec_driver_sql("SELECT COUNT(*) FROM publication").scalar()
            opportunities = connection.exec_driver_sql("SELECT COUNT(*) FROM opportunity").scalar()
    finally:
        engine.dispose()
    assert publications == 0
    assert opportunities == 0


def test_shadow_accepts_a_review_without_a_commercial_send(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id, _ = _reviewed_candidate(client)

    response = _post_review(client, candidate_id, human_decision="APPROVE", reason="ok")

    assert response.status_code == 201
    automation = response.json()["automation"]
    assert automation["automation_mode"] == "SHADOW"
    assert automation["publish_allowed"] is False
    assert automation["publish_reason_code"] in {
        "SHADOW_NO_COMMERCIAL_SEND",
        "POLICY_UNKNOWN",
    }
    assert response.json()["human_review"]["publication_authorized"] is False


def test_invalid_action_returns_structured_error_without_partial_mutation(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id, _ = _reviewed_candidate(client)

    response = _post_review(client, candidate_id, human_decision="PUBLISH", reason="?")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-UI-001"
    assert "EDIT_CONTENT" in response.json()["error"]["context"]["allowed"]
    assert client.get(f"/candidates/{candidate_id}/human-reviews").json()["count"] == 0


def test_ai_review_of_another_candidate_is_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    first, _ = _reviewed_candidate(client)
    second = _capture(client, title="Outro")
    _evaluate(client, second)
    other_ai = _ai_review(client, second)

    response = _post_review(client, first, ai_review_id=other_ai["ai_review_id"])

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-UI-001"
    assert client.get(f"/candidates/{first}/human-reviews").json()["count"] == 0


def test_unknown_candidate_and_review_return_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    detail = client.get("/review/candidates/cand_missing")
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "RAD-UI-003"

    review = client.get("/human-reviews/hr_missing")
    assert review.status_code == 404
    assert review.json()["error"]["code"] == "RAD-UI-002"

    listing = client.get("/candidates/cand_missing/human-reviews")
    assert listing.status_code == 404
    assert listing.json()["error"]["code"] == "RAD-UI-003"


def test_unsupported_schema_version_is_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id, _ = _reviewed_candidate(client)

    response = _post_review(client, candidate_id, schema_version="2.0")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-UI-001"


def test_empty_inbox_is_a_real_empty_state(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    response = client.get("/review/inbox")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["items"] == []


def test_review_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id, _ = _reviewed_candidate(client)

    response = client.post(
        f"/candidates/{candidate_id}/human-reviews",
        json={
            "schema_version": "1.0",
            "human_decision": "APPROVE",
            "reason": "ok",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
