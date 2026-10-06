from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.domain.workflow import WorkflowPolicy, build_workflow_policy
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _client(database_url: str, workflow_policy: WorkflowPolicy | None = None) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            workflow_policy=workflow_policy,
        )
    )


def _capture_payload(**overrides: Any) -> dict[str, Any]:
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


def _capture(client: TestClient) -> str:
    response = client.post("/captures/manual", json=_capture_payload())
    assert response.status_code == 201, response.text
    return response.json()["candidate_id"]


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


def _evaluate(
    client: TestClient,
    candidate_id: str,
    *,
    deal: dict[str, int],
    confidence: dict[str, int],
) -> dict[str, Any]:
    response = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json={
            "schema_version": "1.0",
            "brand": "RADAR_BEAUTY",
            "deal": deal,
            "confidence": confidence,
        },
        headers={"X-Correlation-ID": "cid-eval"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _advance(client: TestClient, candidate_id: str) -> tuple[int, dict[str, Any]]:
    response = client.post(
        f"/candidates/{candidate_id}/opportunities",
        json={"schema_version": "1.0", "priority": 5},
        headers={"X-Correlation-ID": "cid-adv"},
    )
    return response.status_code, response.json()


def _approved_candidate(client: TestClient) -> str:
    candidate_id = _capture(client)
    _evaluate(client, candidate_id, deal=_components(100), confidence=_confidence(100))
    return candidate_id


def test_approved_candidate_creates_opportunity_and_next_step(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)

    status_code, body = _advance(client, candidate_id)

    assert status_code == 201
    assert body["status"] == "OPPORTUNITY_CREATED"
    assert body["decision"] == "APPROVE"
    assert body["correlation_id"] == "cid-adv"
    assert body["plan"]["next_job_type"] == "GENERATE_AFFILIATE_LINK"
    assert body["opportunity"]["state"] == "LINK_PENDING"
    assert body["opportunity"]["priority"] == 5
    assert body["next_job"]["type"] == "GENERATE_AFFILIATE_LINK"
    assert body["next_job"]["status"] == "PENDING"
    assert body["next_job"]["locked_by"] is None
    assert body["next_job"]["entity_type"] == "opportunity"
    assert body["next_job"]["entity_id"] == body["opportunity"]["opportunity_id"]

    # The engine created the next step; no worker is involved (AUT-119).
    assert body["next_job"]["attempts"] == 0

    detail = client.get(f"/opportunities/{body['opportunity']['opportunity_id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["opportunity"]["state"] == "LINK_PENDING"
    event_types = [event["event_type"] for event in detail_body["history"]]
    assert "OPPORTUNITY_CREATED" in event_types
    assert "WORKFLOW_NEXT_JOB_ENQUEUED" in event_types

    listing = client.get(f"/candidates/{candidate_id}/opportunities")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1


def test_rejected_candidate_never_creates_an_opportunity(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)
    _evaluate(client, candidate_id, deal=_components(0), confidence=_confidence(100))

    status_code, body = _advance(client, candidate_id)

    assert status_code == 200
    assert body["status"] == "REJECTED"
    assert body["opportunity"] is None
    assert body["next_job"] is None
    assert client.get(f"/candidates/{candidate_id}/opportunities").json()["count"] == 0


def test_candidate_only_in_processing_is_not_advanced(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)  # Candidate state NEW, no Evaluation yet

    response = client.post(
        f"/candidates/{candidate_id}/opportunities", json={"schema_version": "1.0"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RAD-CAP-013"
    assert client.get(f"/candidates/{candidate_id}/opportunities").json()["count"] == 0


def test_review_requires_human_resolution_without_changing_evaluation(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)
    review = _evaluate(client, candidate_id, deal=_components(60), confidence=_confidence(60))
    assert review["decision"] == "REVIEW"

    status_code, body = _advance(client, candidate_id)

    assert status_code == 200
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["opportunity"] is None
    assert body["human_action"]["action_type"] == "REVIEW_CANDIDATE"
    assert body["human_action"]["entity_id"] == candidate_id

    # The old Evaluation is preserved and a later approval advances.
    first_listing = client.get(f"/candidates/{candidate_id}/evaluations").json()
    assert first_listing["count"] == 1
    assert first_listing["evaluations"][0]["evaluation_id"] == review["evaluation_id"]
    assert first_listing["evaluations"][0]["decision"] == "REVIEW"

    _evaluate(client, candidate_id, deal=_components(100), confidence=_confidence(100))
    status_code, body = _advance(client, candidate_id)
    assert status_code == 201
    assert body["status"] == "OPPORTUNITY_CREATED"

    second_listing = client.get(f"/candidates/{candidate_id}/evaluations").json()
    assert second_listing["count"] == 2
    assert second_listing["evaluations"][0]["evaluation_id"] == review["evaluation_id"]
    assert second_listing["evaluations"][0]["decision"] == "REVIEW"


def test_invalid_transition_is_rejected_and_audited(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)
    _, created = _advance(client, candidate_id)
    opportunity_id = created["opportunity"]["opportunity_id"]

    rejected = client.post(
        f"/opportunities/{opportunity_id}/transitions",
        json={"schema_version": "1.0", "target_state": "PUBLISHED"},
        headers={"X-Correlation-ID": "cid-bad"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "RAD-WF-015"
    assert rejected.json()["error"]["context"]["current_state"] == "LINK_PENDING"
    assert rejected.json()["error"]["context"]["target_state"] == "PUBLISHED"

    history = client.get(f"/opportunities/{opportunity_id}").json()["history"]
    rejected_events = [
        event for event in history if event["event_type"] == "OPPORTUNITY_TRANSITION_REJECTED"
    ]
    assert len(rejected_events) == 1
    assert rejected_events[0]["correlation_id"] == "cid-bad"

    valid = client.post(
        f"/opportunities/{opportunity_id}/transitions",
        json={"schema_version": "1.0", "target_state": "LINK_READY"},
    )
    assert valid.status_code == 200
    assert valid.json()["opportunity"]["state"] == "LINK_READY"


def test_unknown_target_state_returns_structured_input_error(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)
    _, created = _advance(client, candidate_id)
    opportunity_id = created["opportunity"]["opportunity_id"]

    response = client.post(
        f"/opportunities/{opportunity_id}/transitions",
        json={"schema_version": "1.0", "target_state": "NOT_A_STATE"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-WF-016"


def test_missing_opportunity_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    response = client.get("/opportunities/opp_missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RAD-WF-014"

    transition = client.post(
        "/opportunities/opp_missing/transitions",
        json={"schema_version": "1.0", "target_state": "LINK_READY"},
    )
    assert transition.status_code == 404
    assert transition.json()["error"]["code"] == "RAD-WF-014"


def test_baseline_reports_the_explicit_ttl_gap(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)

    _, body = _advance(client, candidate_id)

    assert body["plan"]["ttl_configured"] is False
    assert any(warning["code"] == "WORKFLOW_TTL_NOT_CONFIGURED" for warning in body["warnings"])


def test_aged_candidate_requires_revalidation_via_public_boundary(
    migrated_database_url: str,
) -> None:
    policy = build_workflow_policy(
        {
            "schema_version": "1.0",
            "policy_version": "workflow-policy-ttl",
            "candidate_ttl_seconds": 1,
        }
    )
    client = _client(migrated_database_url, policy)
    candidate_id = _approved_candidate(client)

    # The Evaluation is created with the real clock; age it past the 1s TTL.
    time.sleep(1.2)

    response = client.post(
        f"/candidates/{candidate_id}/opportunities", json={"schema_version": "1.0"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RAD-WF-005"
    assert response.json()["error"]["retryable"] is False
    assert client.get(f"/candidates/{candidate_id}/opportunities").json()["count"] == 0


def test_advance_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)

    response = client.post(
        f"/candidates/{candidate_id}/opportunities", json={"schema_version": "1.0"}
    )
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"


def test_unsupported_schema_version_is_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate(client)

    response = client.post(
        f"/candidates/{candidate_id}/opportunities",
        json={"schema_version": "2.0"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-WF-016"
