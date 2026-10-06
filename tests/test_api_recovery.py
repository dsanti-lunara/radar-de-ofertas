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
        "payload": {},
    }
    body.update(overrides)
    response = client.post("/jobs", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_recovery_run_contract_and_state(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.post("/recovery", json={"schema_version": "1.0"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "RECOVERED"
    assert body["trigger"] == "STARTUP"
    assert body["unclean_shutdown"] is False
    assert body["jobs_requeued"] == 0
    assert body["jobs_blocked"] == 0
    assert body["locks_cleared"] == 0
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
    assert body["state"]["clean_shutdown"] is False
    assert body["state"]["recovery_count"] == 1

    status = client.get("/recovery")
    assert status.status_code == 200
    assert status.json()["status"] == "OK"
    assert status.json()["state"]["recovery_count"] == 1


def test_recovery_detects_unclean_shutdown_via_public_boundary(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    first = client.post("/recovery", json={"schema_version": "1.0"}).json()
    assert first["unclean_shutdown"] is False

    second = client.post("/recovery", json={"schema_version": "1.0", "trigger": "MANUAL"}).json()
    assert second["unclean_shutdown"] is True
    assert second["trigger"] == "MANUAL"
    assert second["state"]["recovery_count"] == 2


def test_clean_shutdown_marker_via_public_boundary(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    client.post("/recovery", json={"schema_version": "1.0"})

    shutdown = client.post("/recovery/clean-shutdown", json={"schema_version": "1.0"})
    assert shutdown.status_code == 200
    assert shutdown.json()["status"] == "CLEAN"
    assert shutdown.json()["state"]["clean_shutdown"] is True

    restarted = client.post("/recovery", json={"schema_version": "1.0"}).json()
    assert restarted["unclean_shutdown"] is False


def test_recovery_requeues_orphan_job_and_old_worker_cannot_confirm(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(client)
    claimed = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-a"})
    assert claimed.status_code == 200
    assert claimed.json()["job_id"] == job["job_id"]

    report = client.post("/recovery", json={"schema_version": "1.0"}).json()
    assert report["jobs_requeued"] == 1

    fetched = client.get(f"/jobs/{job['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "PENDING"
    assert fetched.json()["locked_by"] is None

    denied = client.post(
        f"/jobs/{job['job_id']}/complete",
        json={"schema_version": "1.0", "worker_id": "worker-a"},
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] in ("RAD-WF-009", "RAD-WF-010")

    recovered = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-b"})
    assert recovered.status_code == 200
    assert recovered.json()["job_id"] == job["job_id"]


def test_recovery_blocks_external_effect_job_and_never_resent(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    job = _enqueue(
        client,
        type="PUBLISH_TELEGRAM",
        entity_type="opportunity",
        entity_id="opp_1",
    )
    client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-a"})
    client.post(
        f"/jobs/{job['job_id']}/start",
        json={"schema_version": "1.0", "worker_id": "worker-a"},
    )

    report = client.post("/recovery", json={"schema_version": "1.0"}).json()
    assert report["jobs_blocked"] == 1
    assert report["jobs_requeued"] == 0

    fetched = client.get(f"/jobs/{job['job_id']}").json()
    assert fetched["status"] == "DEAD"

    no_resend = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-b"})
    assert no_resend.status_code == 409
    assert no_resend.json()["error"]["code"] == "RAD-WF-008"


def test_invalid_recovery_input_returns_structured_error(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    bad_schema = client.post("/recovery", json={"schema_version": "2.0"})
    assert bad_schema.status_code == 422
    assert bad_schema.json()["error"]["code"] == "RAD-WF-019"

    bad_trigger = client.post("/recovery", json={"schema_version": "1.0", "trigger": "SOMETHING"})
    assert bad_trigger.status_code == 422
    assert bad_trigger.json()["error"]["code"] == "RAD-WF-019"


def test_recovery_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.post("/recovery", json={"schema_version": "1.0"})
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
