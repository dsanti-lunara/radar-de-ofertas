"""Jobs/Dead Jobs listing read model (RDR-065)."""

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


def _enqueue(client: TestClient, job_type: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "type": job_type,
        "payload": {"candidate_id": "cand_1"},
        "entity_type": "candidate",
        "entity_id": "cand_1",
    }
    body.update(overrides)
    response = client.post("/jobs", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_jobs_listing_reports_real_statuses_and_dead_jobs(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    retry = _enqueue(client, "NORMALIZE_CAPTURE")
    dead_source = _enqueue(client, "PUBLISH_TELEGRAM", max_attempts=1)

    # First claim takes the oldest job; it fails transiently into RETRY_WAIT.
    first = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-a"})
    assert first.json()["job_id"] == retry["job_id"]
    assert (
        client.post(
            f"/jobs/{retry['job_id']}/fail",
            json={"schema_version": "1.0", "worker_id": "worker-a", "error_code": "RAD-WF-001"},
        ).json()["status"]
        == "RETRY_WAIT"
    )

    # The RETRY_WAIT job is not claimable yet, so the next claim takes the second.
    second = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-b"})
    assert second.json()["job_id"] == dead_source["job_id"]
    failed = client.post(
        f"/jobs/{dead_source['job_id']}/fail",
        json={"schema_version": "1.0", "worker_id": "worker-b", "error_code": "RAD-WF-001"},
    )
    assert failed.json()["status"] == "DEAD"

    pending = _enqueue(client, "NORMALIZE_CAPTURE")

    listed = client.get("/jobs")
    assert listed.status_code == 200
    body = listed.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "OK"
    assert body["count"] == 3
    statuses = {job["job_id"]: job["status"] for job in body["jobs"]}
    assert statuses == {
        retry["job_id"]: "RETRY_WAIT",
        dead_source["job_id"]: "DEAD",
        pending["job_id"]: "PENDING",
    }

    dead = client.get("/jobs", params={"status": "DEAD"})
    assert dead.status_code == 200
    assert dead.json()["count"] == 1
    assert dead.json()["jobs"][0]["job_id"] == dead_source["job_id"]
    assert dead.json()["jobs"][0]["status"] == "DEAD"

    running = client.get("/jobs", params={"status": "RUNNING"})
    assert running.status_code == 200
    assert running.json()["count"] == 0
    assert running.json()["jobs"] == []


def test_jobs_listing_rejects_invalid_filter_and_limit(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    invalid_status = client.get("/jobs", params={"status": "NOPE"})
    assert invalid_status.status_code == 422
    assert invalid_status.json()["error"]["code"] == "RAD-WF-006"

    invalid_limit = client.get("/jobs", params={"limit": 0})
    assert invalid_limit.status_code == 422
    assert invalid_limit.json()["error"]["code"] == "RAD-WF-006"


def test_jobs_listing_correlation_id_is_echoed(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.get("/jobs", headers={"X-Correlation-ID": "cid-jobs"})
    assert response.status_code == 200
    assert response.json()["correlation_id"] == "cid-jobs"
    assert response.headers["X-Correlation-ID"] == "cid-jobs"
    assert response.headers["cache-control"] == "no-store"
