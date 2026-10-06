from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from radar.application.operations_service import OperationsService
from radar.domain.audit import (
    EXTERNAL_ACTION_BLOCKED,
    EXTERNAL_ACTIONS_RESUMED,
    EXTERNAL_ACTIONS_STOPPED,
    INTEGRATION_HEALTH_CHANGED,
    OPERATIONS_MODE_CHANGED,
)
from radar.domain.operations import (
    REASON_ALLOWED,
    REASON_SHADOW_NO_COMMERCIAL_SEND,
    REASON_STOP_EXTERNAL_ACTIONS,
    AutomationMode,
    ExternalAction,
    ExternalActionRequest,
    GlobalMode,
    IntegrationState,
    build_automation_policy,
    build_compliance_policy,
)
from radar.infrastructure.models import AuditEventRow
from radar.infrastructure.operations_repository import SqlAlchemyOperationsRepository

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _service(engine: Engine, *, mode: AutomationMode = AutomationMode.AUTO) -> OperationsService:
    return OperationsService(
        store=SqlAlchemyOperationsRepository(engine=engine),
        automation_policy=build_automation_policy(
            {"schema_version": "1.0", "policy_version": "a1", "default_mode": mode.value}
        ),
        compliance_policy=build_compliance_policy(
            {"schema_version": "1.0", "policy_version": "c1", "status": "ACTIVE"}
        ),
        clock=lambda: FIXED_NOW,
    )


def _audit_count(engine: Engine, event_type: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                select(func.count())
                .select_from(AuditEventRow)
                .where(AuditEventRow.event_type == event_type)
            ).scalar_one()
        )


def test_default_state_is_running_and_kill_switch_released(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    state = service.state()
    assert state.global_mode is GlobalMode.RUNNING
    assert state.stop_external_actions is False
    assert state.updated_at is None


def test_set_global_mode_persists_and_audits(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    service.set_global_mode(GlobalMode.DRAINING, reason="upgrade", correlation_id="cid-mode")

    reloaded = _service(migrated_engine).state()
    assert reloaded.global_mode is GlobalMode.DRAINING
    assert reloaded.reason == "upgrade"
    assert reloaded.updated_at == FIXED_NOW

    assert _audit_count(migrated_engine, OPERATIONS_MODE_CHANGED) == 1
    with migrated_engine.connect() as connection:
        payload = connection.execute(
            select(AuditEventRow.payload).where(AuditEventRow.event_type == OPERATIONS_MODE_CHANGED)
        ).scalar_one()
    assert payload is not None
    assert "DRAINING" in payload
    assert "RUNNING" in payload


def test_stop_and_release_kill_switch_persist_and_audit(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    stopped = service.engage_stop(reason="incident", correlation_id="cid-stop")
    assert stopped.stop_external_actions is True
    assert _service(migrated_engine).state().stop_external_actions is True

    released = service.release_stop(reason="resolved", correlation_id="cid-release")
    assert released.stop_external_actions is False
    assert _service(migrated_engine).state().stop_external_actions is False

    assert _audit_count(migrated_engine, EXTERNAL_ACTIONS_STOPPED) == 1
    assert _audit_count(migrated_engine, EXTERNAL_ACTIONS_RESUMED) == 1


def test_integration_health_is_isolated_per_integration(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    service.set_integration_health(
        "telegram", IntegrationState.OFFLINE, summary="down", correlation_id="cid-tg"
    )
    service.set_integration_health(
        "whatsapp", IntegrationState.ONLINE, summary="up", correlation_id="cid-wa"
    )

    names = {item.name: item.state for item in service.list_integrations()}
    assert names == {"telegram": IntegrationState.OFFLINE, "whatsapp": IntegrationState.ONLINE}
    assert _audit_count(migrated_engine, INTEGRATION_HEALTH_CHANGED) == 2

    telegram = service.authorize(
        ExternalActionRequest(
            action=ExternalAction.PUBLISH,
            integration="telegram",
            publication_approved=True,
        ),
        correlation_id="cid-auth-tg",
    )
    assert telegram.allowed is False
    assert telegram.reason_code == "INTEGRATION_UNAVAILABLE"

    whatsapp = service.authorize(
        ExternalActionRequest(
            action=ExternalAction.PUBLISH,
            integration="whatsapp",
            publication_approved=True,
        ),
        correlation_id="cid-auth-wa",
    )
    assert whatsapp.allowed is True
    assert whatsapp.reason_code == REASON_ALLOWED


def test_authorize_uses_the_persisted_kill_switch(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    service.engage_stop(reason="incident", correlation_id="cid-stop")

    decision = service.authorize(
        ExternalActionRequest(action=ExternalAction.BROWSER, publication_approved=True),
        correlation_id="cid-auth",
    )
    assert decision.allowed is False
    assert decision.reason_code == REASON_STOP_EXTERNAL_ACTIONS
    assert decision.stop_external_actions is True


def test_authorize_audits_external_decisions_only(migrated_engine: Engine) -> None:
    service = _service(migrated_engine, mode=AutomationMode.SHADOW)

    blocked = service.authorize(
        ExternalActionRequest(action=ExternalAction.PUBLISH, publication_approved=True),
        correlation_id="cid-block",
    )
    assert blocked.allowed is False
    assert blocked.reason_code == REASON_SHADOW_NO_COMMERCIAL_SEND
    assert _audit_count(migrated_engine, EXTERNAL_ACTION_BLOCKED) == 1

    service.authorize(
        ExternalActionRequest(action=ExternalAction.READ),
        correlation_id="cid-read",
    )
    assert _audit_count(migrated_engine, EXTERNAL_ACTION_BLOCKED) == 1
