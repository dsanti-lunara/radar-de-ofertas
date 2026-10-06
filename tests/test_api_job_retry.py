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


def _enqueue(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "type": "NORMALIZE_CAPTURE",
        "payload": {"candidate_id": "cand_1"},
        "entity_type": "candidate",
        "entity_id": "cand_1",
    }
    body.update(overrides)
    response = client.post("/jobs", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _claim(client: TestClient, worker_id: str = "worker-a") -> dict[str, Any]:
    response = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": worker_id})
    assert response.status_code == 200, response.text
    return response.json()


def _fail(client: TestClient, job_id: str, *, worker_id: str, error_code: str):
    return client.post(
        f"/jobs/{job_id}/fail",
        json={"schema_version": "1.0", "worker_id": worker_id, "error_code": error_code},
    )


def test_transient_failure_schedules_backoff_from_the_public_boundary(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client, max_attempts=3)
    claimed = _claim(client)
    assert claimed["attempts"] == 1

    response = _fail(client, job["job_id"], worker_id="worker-a", error_code="RAD-WF-001")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "RETRY_WAIT"
    assert body["failure"]["failure_class"] == "TRANSIENT"
    assert body["failure"]["action"] == "RETRY_WAIT"
    assert body["failure"]["retryable"] is True
    assert body["failure"]["delay_seconds"] == 30
    assert body["failure"]["available_at"] == body["available_at"]
    assert body["human_action"] is None

    fetched = client.get(f"/jobs/{job['job_id']}")
    assert fetched.json()["status"] == "RETRY_WAIT"

    # The backoff is honored: the job is not available yet.
    again = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-b"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "RAD-WF-008"


def test_exhaustion_returns_dead_and_creates_a_queryable_human_action(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client, max_attempts=1, type="PUBLISH_TELEGRAM")
    _claim(client)

    response = _fail(client, job["job_id"], worker_id="worker-a", error_code="RAD-WF-001")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "DEAD"
    assert body["failure"]["failure_class"] == "TRANSIENT"
    assert body["failure"]["retryable"] is False
    assert body["failure"]["resolution_code"] == "RAD-WF-003"
    action = body["human_action"]
    assert action is not None
    assert action["action_type"] == "DEAD_JOB_REVIEW"
    assert action["status"] == "OPEN"
    assert action["entity_type"] == "candidate"
    assert action["entity_id"] == "cand_1"
    assert action["impact"] and action["next_steps"]

    listed = client.get("/human-actions")
    assert listed.status_code == 200
    actions = listed.json()["human_actions"]
    assert [item["human_action_id"] for item in actions] == [action["human_action_id"]]

    fetched = client.get(f"/human-actions/{action['human_action_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "OPEN"
    assert fetched.json()["error_code"] == "RAD-WF-001"

    missing = client.get("/human-actions/ha_missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RAD-WF-011"

    # The job was not recreated and the state is terminal.
    assert client.get(f"/jobs/{job['job_id']}").json()["status"] == "DEAD"
    assert (
        client.post(
            "/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-b"}
        ).status_code
        == 409
    )


def test_auth_required_does_not_loop(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client, max_attempts=5, type="AI_REVIEW")
    _claim(client)

    response = _fail(client, job["job_id"], worker_id="worker-a", error_code="RAD-AI-001")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "DEAD"
    assert body["failure"]["failure_class"] == "HUMAN_REQUIRED"
    assert body["failure"]["retryable"] is False
    assert body["failure"]["delay_seconds"] is None
    assert body["human_action"]["action_type"] == "RESTORE_AI_AUTH"
    assert response.json()["attempts"] == 1

    no_loop = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-b"})
    assert no_loop.status_code == 409


def test_permanent_failure_does_not_retry(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client, max_attempts=5)
    _claim(client)

    response = _fail(client, job["job_id"], worker_id="worker-a", error_code="RAD-CAP-004")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["failure"]["failure_class"] == "PERMANENT"
    assert body["failure"]["retryable"] is False
    assert body["failure"]["delay_seconds"] is None
    assert body["human_action"] is None
    assert (
        client.post(
            "/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-b"}
        ).status_code
        == 409
    )


def test_foreign_worker_cannot_report_the_failure(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client)
    _claim(client, "worker-a")

    denied = _fail(client, job["job_id"], worker_id="worker-b", error_code="RAD-WF-001")
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "RAD-WF-009"
    assert client.get(f"/jobs/{job['job_id']}").json()["status"] == "CLAIMED"


def test_missing_error_code_returns_structured_workflow_error(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client)
    _claim(client)

    response = client.post(
        f"/jobs/{job['job_id']}/fail",
        json={"schema_version": "1.0", "worker_id": "worker-a"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-WF-006"


def test_human_action_status_filter_and_invalid_status(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client, max_attempts=1)
    _claim(client)
    response = _fail(client, job["job_id"], worker_id="worker-a", error_code="RAD-WF-001")
    assert response.status_code == 200

    open_actions = client.get("/human-actions", params={"status": "OPEN"})
    assert open_actions.status_code == 200
    assert len(open_actions.json()["human_actions"]) == 1

    resolved = client.get("/human-actions", params={"status": "RESOLVED"})
    assert resolved.status_code == 200
    assert resolved.json()["human_actions"] == []

    invalid = client.get("/human-actions", params={"status": "NOPE"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "RAD-WF-006"
