"""Human Actions center: audited resolution through the public boundary (RDR-063)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.api.app import create_app
from radar.domain.human_action import build_human_action
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.human_action_repository import human_action_to_row
from radar.infrastructure.models import AuditEventRow, HumanActionRow
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _client(database_url: str) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(create_app(settings=settings, engine=engine))


def _enqueue(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/jobs",
        json={
            "schema_version": "1.0",
            "type": "PUBLISH_TELEGRAM",
            "payload": {"candidate_id": "cand_1"},
            "entity_type": "candidate",
            "entity_id": "cand_1",
            "max_attempts": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _dead_job_action(client: TestClient) -> dict[str, Any]:
    job = _enqueue(client)
    assert (
        client.post(
            "/jobs/claim", json={"schema_version": "1.0", "worker_id": "worker-a"}
        ).status_code
        == 200
    )
    response = client.post(
        f"/jobs/{job['job_id']}/fail",
        json={"schema_version": "1.0", "worker_id": "worker-a", "error_code": "RAD-WF-001"},
    )
    assert response.status_code == 200, response.text
    action = response.json()["human_action"]
    assert action["action_type"] == "DEAD_JOB_REVIEW"
    return action


def _insert_action(database_url: str, action: Any) -> None:
    engine = create_database_engine(database_url)
    with Session(engine) as session, session.begin():
        session.add(human_action_to_row(action))
    engine.dispose()


def test_resolve_acknowledges_the_intervention_and_is_idempotent(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    action = _dead_job_action(client)
    assert action["status"] == "OPEN"
    # The contract explains the resolution without inventing a capability.
    assert action["resolution"]["resolvable_via_center"] is True
    assert action["resolution"]["mode"] == "OPERATOR_ACK"

    resolved = client.post(
        f"/human-actions/{action['human_action_id']}/resolve",
        json={"schema_version": "1.0", "reason": "Job reprocessado manualmente"},
        headers={"X-Correlation-ID": "cid-ha"},
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "RESOLVED"
    assert body["idempotent_replay"] is False
    assert body["human_action"]["status"] == "RESOLVED"
    assert body["correlation_id"] == "cid-ha"
    assert resolved.headers["X-Correlation-ID"] == "cid-ha"
    assert resolved.headers["cache-control"] == "no-store"

    # The action is terminal and retrying does not duplicate the audit event.
    replay = client.post(
        f"/human-actions/{action['human_action_id']}/resolve",
        json={"schema_version": "1.0", "reason": "Repetição"},
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "ALREADY_RESOLVED"
    assert replay.json()["idempotent_replay"] is True

    fetched = client.get(f"/human-actions/{action['human_action_id']}")
    assert fetched.json()["status"] == "RESOLVED"
    open_actions = client.get("/human-actions", params={"status": "OPEN"})
    assert open_actions.json()["human_actions"] == []

    engine = create_database_engine(migrated_database_url)
    with Session(engine) as session:
        count = session.execute(
            select(func.count())
            .select_from(AuditEventRow)
            .where(AuditEventRow.event_type == "HUMAN_ACTION_RESOLVED")
        ).scalar_one()
    engine.dispose()
    assert count == 1


def test_delegated_publication_action_cannot_be_closed_from_the_center(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    action = build_human_action(
        action_type="REVIEW_PUBLICATION",
        entity_type="publication",
        entity_id="pub_1",
        reason="SEND_RESULT_UNKNOWN",
        error_code="RAD-PUB-006",
        correlation_id="cid-pub",
        now=datetime(2026, 10, 6, 12, 0, tzinfo=UTC),
    )
    _insert_action(migrated_database_url, action)

    fetched = client.get(f"/human-actions/{action.id}").json()
    assert fetched["resolution"]["resolvable_via_center"] is False
    assert fetched["resolution"]["mode"] == "PUBLICATION_RESOLUTION"

    denied = client.post(
        f"/human-actions/{action.id}/resolve",
        json={"schema_version": "1.0", "reason": "Enviado"},
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "RAD-WF-020"
    assert denied.json()["error"]["retryable"] is False
    # Fail closed: the action stays OPEN and no resolution is audited.
    assert client.get(f"/human-actions/{action.id}").json()["status"] == "OPEN"

    engine = create_database_engine(migrated_database_url)
    with Session(engine) as session:
        count = session.execute(
            select(func.count())
            .select_from(AuditEventRow)
            .where(AuditEventRow.event_type == "HUMAN_ACTION_RESOLVED")
        ).scalar_one()
        row = session.get(HumanActionRow, action.id)
        assert row is not None and row.status == "OPEN"
    engine.dispose()
    assert count == 0


def test_resolve_validates_input_and_missing_action(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    missing = client.post(
        "/human-actions/ha_missing/resolve",
        json={"schema_version": "1.0", "reason": "x"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RAD-WF-011"

    empty = client.post(
        "/human-actions/ha_missing/resolve",
        json={"schema_version": "1.0", "reason": ""},
    )
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "RAD-WF-006"

    bad_schema = client.post(
        "/human-actions/ha_missing/resolve",
        json={"schema_version": "9.9", "reason": "x"},
    )
    assert bad_schema.status_code == 422
