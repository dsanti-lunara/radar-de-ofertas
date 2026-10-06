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
        "priority": 4,
        "payload": {"candidate_id": "cand_1"},
        "entity_type": "candidate",
        "entity_id": "cand_1",
    }
    body.update(overrides)
    response = client.post("/jobs", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_enqueue_returns_pending_job_with_persisted_fields(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    response = client.post(
        "/jobs",
        json={
            "schema_version": "1.0",
            "type": "NORMALIZE_CAPTURE",
            "priority": 9,
            "max_attempts": 2,
            "available_at": "2026-10-05T12:00:00+00:00",
            "payload": {"offer_id": "off_1"},
        },
        headers={"X-Correlation-ID": "cid-job"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "PENDING"
    assert body["type"] == "NORMALIZE_CAPTURE"
    assert body["priority"] == 9
    assert body["attempts"] == 0
    assert body["max_attempts"] == 2
    assert body["available_at"] == "2026-10-05T12:00:00+00:00"
    assert body["correlation_id"] == "cid-job"
    assert body["payload"] == {"offer_id": "off_1"}
    assert body["job_id"].startswith("job_")
    assert response.headers["X-Correlation-ID"] == "cid-job"


def test_claim_grants_one_lease_then_no_job_is_available(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client)

    first = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-a"})
    assert first.status_code == 200, first.text
    claimed = first.json()
    assert claimed["job_id"] == job["job_id"]
    assert claimed["status"] == "CLAIMED"
    assert claimed["attempts"] == 1
    assert claimed["locked_by"] == "worker-a"
    assert claimed["lease_expires_at"] is not None

    second = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-b"})
    assert second.status_code == 409
    error = second.json()
    assert error["error"]["code"] == "RAD-WF-008"
    assert error["error"]["retryable"] is True

    fetched = client.get(f"/jobs/{job['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "CLAIMED"


def test_invalid_worker_cannot_complete_anothers_execution(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client)
    client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-a"})

    denied = client.post(
        f"/jobs/{job['job_id']}/complete",
        json={"schema_version": "1.0", "worker_id": "worker-b"},
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "RAD-WF-009"

    client.post(
        f"/jobs/{job['job_id']}/start",
        json={"schema_version": "1.0", "worker_id": "worker-a"},
    )
    done = client.post(
        f"/jobs/{job['job_id']}/complete",
        json={"schema_version": "1.0", "worker_id": "worker-a"},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "SUCCESS"


def test_domain_state_is_never_accepted_as_a_job_state(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    response = client.post("/jobs", json={"schema_version": "1.0", "type": "NEW", "payload": {}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-WF-006"

    # Nothing was persisted: claiming still finds no job.
    empty = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-a"})
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "RAD-WF-008"


def test_invalid_schema_version_is_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.post(
        "/jobs",
        json={"schema_version": "9.9", "type": "NORMALIZE_CAPTURE", "payload": {}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-WF-006"


def test_missing_job_type_returns_structured_workflow_error(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    response = client.post("/jobs", json={"schema_version": "1.0", "payload": {}})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "RAD-WF-006"
    assert "type" in body["error"]["context"]["fields"][0]


def test_sensitive_payload_is_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.post(
        "/jobs",
        json={
            "schema_version": "1.0",
            "type": "NORMALIZE_CAPTURE",
            "payload": {"cookie": "session"},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-WF-006"


def test_unknown_job_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.get("/jobs/job_missing")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RAD-WF-007"
    assert body["error"]["retryable"] is False


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.post(
        "/jobs", json={"schema_version": "1.0", "type": "CALCULATE_SCORES", "payload": {}}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["X-Correlation-ID"] == body["correlation_id"]


def test_logical_lock_boundary_is_exclusive(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    first = client.post(
        "/locks",
        json={
            "schema_version": "1.0",
            "name": "queue:general",
            "owner": "worker-a",
            "ttl_seconds": 60,
        },
    )
    assert first.status_code == 201, first.text
    acquired = first.json()
    assert acquired["status"] == "ACQUIRED"
    assert acquired["name"] == "queue:general"
    assert acquired["owner"] == "worker-a"
    assert acquired["expires_at"] is not None

    second = client.post(
        "/locks",
        json={
            "schema_version": "1.0",
            "name": "queue:general",
            "owner": "worker-b",
            "ttl_seconds": 60,
        },
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "RAD-WF-004"

    released = client.delete("/locks/queue:general", params={"owner": "worker-a"})
    assert released.status_code == 200
    assert released.json()["status"] == "RELEASED"
