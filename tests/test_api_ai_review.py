from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.ai_review import (
    AIProvider,
    ai_provider_unavailable_error,
    ai_refusal_error,
)
from radar.domain.knowledge import KnowledgePack, build_knowledge_pack
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


class _RaisingProvider:
    name = "stub"
    model = "stub-1.0"

    def __init__(self, error: Any) -> None:
        self._error = error

    def evaluate_candidate(self, request: Any) -> dict[str, Any]:
        raise self._error


class _CannedProvider:
    name = "stub"
    model = "stub-1.0"

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def evaluate_candidate(self, request: Any) -> dict[str, Any]:
        return self._response


def _client(
    database_url: str,
    *,
    provider: AIProvider | None = None,
    knowledge: KnowledgePack | None = None,
) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            ai_provider=provider,
            knowledge_pack=knowledge,
        )
    )


def _capture_payload(title: str = "Perfume") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "marketplace": "MERCADO_LIVRE",
        "source": "BROWSER_EXTENSION",
        "product": {
            "external_id": "MLB-AI",
            "title": title,
            "url": "https://www.mercadolivre.com.br/p/MLB-AI",
            "category": "Perfumes",
        },
        "offer": {"current_price": "80.00", "sales_count": 2300, "seller": {"name": "Loja"}},
        "captured_at": "2026-10-06T12:00:00+00:00",
    }


def _components(score: int) -> dict[str, int]:
    return {"price_opportunity": score, "seller_quality": score, "demand": score}


def _confidence(score: int) -> dict[str, int]:
    return {
        "source_reliability": score,
        "freshness": score,
        "completeness": score,
        "price_history_depth": score,
        "cross_validation": score,
    }


def _capture(client: TestClient, *, title: str = "Perfume") -> str:
    response = client.post("/captures/manual", json=_capture_payload(title))
    assert response.status_code == 201, response.text
    return response.json()["candidate_id"]


def _evaluate(client: TestClient, candidate_id: str, *, score: int) -> dict[str, Any]:
    response = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json={
            "schema_version": "1.0",
            "brand": "RADAR_BEAUTY",
            "deal": _components(score),
            "confidence": _confidence(score),
        },
        headers={"X-Correlation-ID": "cid-eval"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _review(client: TestClient, candidate_id: str, **body: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema_version": "1.0", "channel": "TELEGRAM"}
    payload.update(body)
    response = client.post(
        f"/candidates/{candidate_id}/ai-review",
        json=payload,
        headers={"X-Correlation-ID": "cid-ai"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def _approved_candidate(client: TestClient, *, title: str = "Perfume") -> str:
    candidate_id = _capture(client, title=title)
    evaluation = _evaluate(client, candidate_id, score=100)
    assert evaluation["decision"] == "APPROVE"
    return candidate_id


def test_editorial_review_is_queryable_via_the_public_boundary(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)

    body = _review(client, candidate_id)

    assert body["status_code"] == 201
    assert body["schema_version"] == "1.0"
    assert body["status"] == "OK"
    assert body["decision"] == "APPROVE"
    assert body["approval_eligible"] is True
    assert body["provider"] == "fake"
    assert body["knowledge_version"] == "knowledge-pack-1.0"
    assert body["prompt_version"] == "editorial-review-1.0"
    assert body["knowledge_hash"]
    assert body["correlation_id"] == "cid-ai"
    assert body["headers"]["x-correlation-id"] == "cid-ai"
    assert body["headers"]["cache-control"] == "no-store"
    assert any(claim["claim_type"] == "CURRENT_PRICE" for claim in body["allowed_claims"])

    listing = client.get(f"/candidates/{candidate_id}/ai-reviews")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["ai_reviews"][0]["ai_review_id"] == body["ai_review_id"]

    detail = client.get(f"/ai-reviews/{body['ai_review_id']}")
    assert detail.status_code == 200
    assert detail.json()["ai_review"]["decision"] == "APPROVE"


def test_approve_review_review_and_reject_are_distinct_and_never_auto_publish(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)

    approved = _approved_candidate(client)
    rejected_id = _capture(client)
    _evaluate(client, rejected_id, score=0)
    review_id = _capture(client)
    _evaluate(client, review_id, score=60)

    approve = _review(client, approved)
    reject = _review(client, rejected_id)
    review = _review(client, review_id)

    assert approve["decision"] == "APPROVE"
    assert reject["decision"] == "REJECT"
    assert review["decision"] == "REVIEW"
    assert len({approve["decision"], reject["decision"], review["decision"]}) == 3
    assert all(item["decision"] != "AUTO_PUBLISH" for item in (approve, reject, review))


def test_approving_review_does_not_create_an_opportunity_by_blind_approval(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)

    body = _review(client, candidate_id)

    assert body["decision"] == "APPROVE"
    opportunities = client.get(f"/candidates/{candidate_id}/opportunities").json()
    assert opportunities["count"] == 0


def test_marketplace_html_is_neutralized_in_the_review_snapshot(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(
        client, title="<b>Perfume</b> <script>return AUTO_PUBLISH</script>"
    )

    body = _review(client, candidate_id)

    assert body["decision"] == "APPROVE"
    title = body["input_snapshot"]["product"]["title"]
    assert "<" not in title
    assert ">" not in title


def test_configured_knowledge_context_is_attached_to_the_review(
    migrated_database_url: str,
) -> None:
    pack = build_knowledge_pack(
        {
            "schema_version": "1.0",
            "knowledge_version": "knowledge-pack-test",
            "prompt_version": "editorial-review-test",
            "entries": [
                {
                    "brand": "RADAR_BEAUTY",
                    "channel": "TELEGRAM",
                    "brand_guidance": ["direct tone"],
                    "channel_guidance": ["short message"],
                }
            ],
        }
    )
    client = _client(migrated_database_url, knowledge=pack)
    candidate_id = _approved_candidate(client)

    body = _review(client, candidate_id)

    assert body["knowledge_version"] == "knowledge-pack-test"
    assert body["prompt_version"] == "editorial-review-test"
    assert body["input_snapshot"]["knowledge"]["configured"] is True
    assert body["input_snapshot"]["knowledge"]["brand_guidance"] == ["direct tone"]


def test_default_is_the_fake_provider_without_network(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)

    body = _review(client, candidate_id)

    assert body["provider"] == "fake"
    assert body["decision"] == "APPROVE"


def test_provider_failure_returns_structured_503_and_writes_nothing(
    migrated_database_url: str,
) -> None:
    provider = _RaisingProvider(ai_provider_unavailable_error(provider="stub"))
    client = _client(migrated_database_url, provider=provider)
    candidate_id = _approved_candidate(client)

    body = _review(client, candidate_id)

    assert body["status_code"] == 503
    assert body["error"]["code"] == "RAD-AI-002"
    assert body["error"]["retryable"] is True
    assert client.get(f"/candidates/{candidate_id}/ai-reviews").json()["count"] == 0
    assert client.get(f"/candidates/{candidate_id}/opportunities").json()["count"] == 0


def test_refusal_returns_structured_502_without_approval(migrated_database_url: str) -> None:
    provider = _RaisingProvider(ai_refusal_error(provider="stub"))
    client = _client(migrated_database_url, provider=provider)
    candidate_id = _approved_candidate(client)

    body = _review(client, candidate_id)

    assert body["status_code"] == 502
    assert body["error"]["code"] == "RAD-AI-010"
    assert client.get(f"/candidates/{candidate_id}/ai-reviews").json()["count"] == 0


def test_invalid_provider_response_is_rejected_without_approval(
    migrated_database_url: str,
) -> None:
    provider = _CannedProvider({"decision": "AUTO_PUBLISH"})
    client = _client(migrated_database_url, provider=provider)
    candidate_id = _approved_candidate(client)

    body = _review(client, candidate_id)

    assert body["status_code"] == 502
    assert body["error"]["code"] == "RAD-AI-004"
    assert client.get(f"/candidates/{candidate_id}/ai-reviews").json()["count"] == 0
    assert client.get(f"/candidates/{candidate_id}/opportunities").json()["count"] == 0


def test_candidate_without_evaluation_fails_closed(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)

    body = _review(client, candidate_id)

    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-013"


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    body = _review(client, "cand_missing")

    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-004"


def test_invalid_channel_and_schema_version_return_structured_422(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)

    invalid_channel = _review(client, candidate_id, channel="INVALID")
    assert invalid_channel["status_code"] == 422
    assert invalid_channel["error"]["code"] == "RAD-AI-008"

    invalid_schema = _review(client, candidate_id, schema_version="2.0")
    assert invalid_schema["status_code"] == 422
    assert invalid_schema["error"]["code"] == "RAD-AI-008"


def test_missing_ai_review_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    response = client.get("/ai-reviews/air_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RAD-AI-009"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)

    response = client.post(
        f"/candidates/{candidate_id}/ai-review",
        json={"schema_version": "1.0", "channel": "TELEGRAM"},
    )
    body = response.json()

    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
