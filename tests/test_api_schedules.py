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


def _create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "name": "nightly-backup",
        "type": "INTERVAL",
        "job_type": "BACKUP_DATABASE",
        "interval_seconds": 3600,
        "payload": {"scope": "full"},
    }
    body.update(overrides)
    response = client.post("/schedules", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_read_schedule_roundtrip(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    created = _create(
        client,
        priority=4,
        timezone="America/Maceio",
        quiet_windows=[{"start": "22:00", "end": "07:00", "days": [0, 1]}],
    )
    assert created["status"] == "CREATED"
    assert created["schema_version"] == "1.0"
    assert created["schedule_id"].startswith("sch_")
    assert created["type"] == "INTERVAL"
    assert created["job_type"] == "BACKUP_DATABASE"
    assert created["priority"] == 4
    assert created["enabled"] is True
    assert created["lock_name"] == "schedule:nightly-backup"
    assert created["quiet_windows"] == [{"start": "22:00", "end": "07:00", "days": [0, 1]}]
    assert created["next_run_at"] is not None

    fetched = client.get(f"/schedules/{created['schedule_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["schedule_id"] == created["schedule_id"]

    listed = client.get("/schedules")
    assert listed.status_code == 200
    body = listed.json()
    assert body["schema_version"] == "1.0"
    assert [item["schedule_id"] for item in body["schedules"]] == [created["schedule_id"]]


def test_invalid_cadence_returns_structured_workflow_error(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    response = client.post(
        "/schedules",
        json={
            "schema_version": "1.0",
            "name": "broken",
            "type": "INTERVAL",
            "job_type": "BACKUP_DATABASE",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-WF-012"


def test_unknown_type_returns_structured_workflow_error(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.post(
        "/schedules",
        json={
            "schema_version": "1.0",
            "name": "broken",
            "type": "EVERY_NOW",
            "job_type": "BACKUP_DATABASE",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-WF-012"


def test_sensitive_payload_is_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.post(
        "/schedules",
        json={
            "schema_version": "1.0",
            "name": "leaky",
            "type": "INTERVAL",
            "job_type": "BACKUP_DATABASE",
            "interval_seconds": 60,
            "payload": {"cookie": "session"},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-WF-012"


def test_unknown_schedule_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    response = client.get("/schedules/sch_missing")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RAD-WF-013"
    assert body["error"]["retryable"] is False


def test_on_demand_tick_creates_pending_job_via_public_boundary(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    schedule = _create(client, name="manual", type="ON_DEMAND", interval_seconds=None)

    ticked = client.post(f"/schedules/{schedule['schedule_id']}/tick")
    assert ticked.status_code == 200, ticked.text
    body = ticked.json()
    assert body["status"] == "TICKED"
    assert body["schema_version"] == "1.0"
    result = body["results"][0]
    assert result["action"] == "ENQUEUE"
    assert result["reason"] == "FORCED"
    assert result["occurrence_count"] == 1
    job = result["job"]
    assert job["status"] == "PENDING"
    assert job["attempts"] == 0
    assert job["type"] == "BACKUP_DATABASE"
    assert job["payload"]["schedule_id"] == schedule["schedule_id"]

    # The created Job is observable through the existing public boundary.
    fetched = client.get(f"/jobs/{job['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "PENDING"


def test_equivalent_lock_defers_tick_via_public_boundary(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    schedule = _create(client, name="locked", type="ON_DEMAND", interval_seconds=None)
    lock = client.post(
        "/locks",
        json={
            "schema_version": "1.0",
            "name": "schedule:locked",
            "owner": "worker-a",
            "ttl_seconds": 600,
        },
    )
    assert lock.status_code == 201

    ticked = client.post(f"/schedules/{schedule['schedule_id']}/tick")
    assert ticked.status_code == 200
    result = ticked.json()["results"][0]
    assert result["action"] == "SKIP_LOCKED"
    assert result["reason"] == "EQUIVALENT_LOCK_HELD"
    assert result["job"] is None

    # No Job was created while the equivalent lock was active.
    empty = client.post("/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-b"})
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "RAD-WF-008"


def test_enable_and_disable_roundtrip(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    schedule = _create(client, name="toggle")

    disabled = client.post(f"/schedules/{schedule['schedule_id']}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"
    assert disabled.json()["enabled"] is False

    enabled = client.post(f"/schedules/{schedule['schedule_id']}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["status"] == "ENABLED"
    assert enabled.json()["enabled"] is True


def test_tick_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    schedule = _create(client, name="corr", type="ON_DEMAND", interval_seconds=None)

    response = client.post(f"/schedules/{schedule['schedule_id']}/tick")
    assert response.status_code == 200
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["X-Correlation-ID"] == body["correlation_id"]
    assert body["results"][0]["correlation_id"] == body["correlation_id"]
