"""AUTO eligibility is fail-closed and never promotes (AUT-257, AUT-258)."""

from __future__ import annotations

from datetime import UTC, datetime

from radar.domain.human_action import build_human_action
from radar.domain.operations import (
    ComplianceStatus,
    IntegrationHealth,
    IntegrationState,
    build_compliance_policy,
)
from radar.domain.settings import AutoEligibilityState, evaluate_auto_eligibility

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _active_compliance():
    return build_compliance_policy(
        {"schema_version": "1.0", "policy_version": "c1", "status": ComplianceStatus.ACTIVE.value}
    )


def _open_action():
    return build_human_action(
        action_type="BACKUP_FAILURE",
        entity_type="backup",
        entity_id="bk_1",
        reason="BACKUP_FAILED",
        error_code="RAD-BKP-001",
        correlation_id="cid-1",
        now=NOW,
    )


def test_unproven_criteria_keep_the_result_ineligible() -> None:
    result = evaluate_auto_eligibility(
        compliance_policy=_active_compliance(),
        integrations=(
            IntegrationHealth(name="telegram", state=IntegrationState.ONLINE, summary="up"),
        ),
        open_human_actions=(),
        now=NOW,
    )
    assert result.eligible is False
    assert result.promotes_automatically is False
    assert result.requires_human_decision is True
    states = {item.criterion_id: item.state for item in result.criteria}
    assert states["compliance_policy"] is AutoEligibilityState.MET
    assert states["integration_health"] is AutoEligibilityState.MET
    assert states["open_human_actions"] is AutoEligibilityState.MET
    assert states["shadow_samples"] is AutoEligibilityState.UNAVAILABLE
    assert states["human_agreement"] is AutoEligibilityState.UNAVAILABLE
    assert states["p0_p1_open"] is AutoEligibilityState.UNAVAILABLE
    assert states["validation_failures"] is AutoEligibilityState.UNAVAILABLE


def test_missing_and_unhealthy_integrations_are_not_met() -> None:
    none_registered = evaluate_auto_eligibility(
        compliance_policy=_active_compliance(),
        integrations=(),
        open_human_actions=(),
        now=NOW,
    )
    by_id = {item.criterion_id: item.state for item in none_registered.criteria}
    assert by_id["integration_health"] is AutoEligibilityState.NOT_MET

    degraded = evaluate_auto_eligibility(
        compliance_policy=_active_compliance(),
        integrations=(
            IntegrationHealth(name="telegram", state=IntegrationState.ONLINE, summary="up"),
            IntegrationHealth(name="shopee", state=IntegrationState.AUTH_REQUIRED, summary="auth"),
        ),
        open_human_actions=(),
        now=NOW,
    )
    by_id = {item.criterion_id: item.state for item in degraded.criteria}
    assert by_id["integration_health"] is AutoEligibilityState.NOT_MET


def test_open_human_actions_and_unknown_compliance_block() -> None:
    blocked = evaluate_auto_eligibility(
        compliance_policy=build_compliance_policy(
            {
                "schema_version": "1.0",
                "policy_version": "c1",
                "status": ComplianceStatus.UNKNOWN.value,
            }
        ),
        integrations=(),
        open_human_actions=(_open_action(),),
        now=NOW,
    )
    by_id = {item.criterion_id: item.state for item in blocked.criteria}
    assert by_id["compliance_policy"] is AutoEligibilityState.NOT_MET
    assert by_id["open_human_actions"] is AutoEligibilityState.NOT_MET
    assert blocked.eligible is False
