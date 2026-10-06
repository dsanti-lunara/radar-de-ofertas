from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from radar.domain.operations import (
    APPROVED_AUTOMATION_POLICY,
    APPROVED_COMPLIANCE_POLICY,
    AUTOMATION_POLICY_INVALID,
    COMPLIANCE_POLICY_INVALID,
    OPERATIONS_INPUT_INVALID,
    REASON_ALLOWED,
    REASON_GLOBAL_MODE_DRAINING,
    REASON_GLOBAL_MODE_MAINTENANCE,
    REASON_GLOBAL_MODE_PAUSED,
    REASON_INTEGRATION_UNAVAILABLE,
    REASON_MANUAL_MODE,
    REASON_POLICY_BLOCK,
    REASON_POLICY_EXPIRED,
    REASON_POLICY_NOT_EFFECTIVE,
    REASON_POLICY_REVIEW_REQUIRED,
    REASON_POLICY_UNKNOWN,
    REASON_PUBLICATION_APPROVAL_REQUIRED,
    REASON_SHADOW_NO_COMMERCIAL_SEND,
    REASON_STOP_EXTERNAL_ACTIONS,
    AutomationMode,
    AutomationPolicy,
    ChannelCompliancePolicy,
    ExternalAction,
    ExternalActionDecision,
    ExternalActionRequest,
    GlobalMode,
    IntegrationHealth,
    IntegrationState,
    OperationalState,
    OperationsError,
    build_automation_policy,
    build_compliance_policy,
    decide_external_action,
)
from radar.domain.taxonomy import Brand

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _active_compliance(**overrides: object) -> ChannelCompliancePolicy:
    document: dict[str, object] = {
        "schema_version": "1.0",
        "policy_version": "c1",
        "status": "ACTIVE",
    }
    document.update(overrides)
    return build_compliance_policy(document)


def _mode_policy(mode: AutomationMode) -> AutomationPolicy:
    return build_automation_policy(
        {
            "schema_version": "1.0",
            "policy_version": "a1",
            "default_mode": mode.value,
        }
    )


def _decide(
    action: ExternalAction,
    *,
    mode: AutomationMode,
    compliance: ChannelCompliancePolicy | None = None,
    state: OperationalState | None = None,
    integration: str | None = None,
    integration_state: IntegrationState | None = None,
    publication_approved: bool = False,
    automation_policy: AutomationPolicy | None = None,
) -> ExternalActionDecision:
    health = (
        None
        if integration_state is None
        else IntegrationHealth(
            name=integration or "integration",
            state=integration_state,
            summary="test",
            updated_at=FIXED_NOW,
        )
    )
    return decide_external_action(
        request=ExternalActionRequest(
            action=action,
            integration=integration,
            publication_approved=publication_approved,
        ),
        operational_state=state or OperationalState(),
        automation_policy=automation_policy or _mode_policy(mode),
        compliance_policy=compliance or _active_compliance(),
        integration_health=health,
        now=FIXED_NOW,
        correlation_id="cid-1",
    )


def test_approved_baseline_is_shadow_and_unknown_compliance() -> None:
    assert APPROVED_AUTOMATION_POLICY.default_mode is AutomationMode.SHADOW
    assert APPROVED_AUTOMATION_POLICY.policy_version == "automation-policy-1.0"
    assert APPROVED_COMPLIANCE_POLICY.status.value == "UNKNOWN"
    assert APPROVED_COMPLIANCE_POLICY.blocking_reason(FIXED_NOW) == REASON_POLICY_UNKNOWN


def test_shadow_never_sends_even_with_publication_approval() -> None:
    decision = _decide(
        ExternalAction.PUBLISH,
        mode=AutomationMode.SHADOW,
        publication_approved=True,
    )
    assert decision.allowed is False
    assert decision.reason_code == REASON_SHADOW_NO_COMMERCIAL_SEND
    assert decision.external is True


def test_assisted_requires_explicit_publication_approval() -> None:
    blocked = _decide(ExternalAction.PUBLISH, mode=AutomationMode.ASSISTED)
    assert blocked.allowed is False
    assert blocked.reason_code == REASON_PUBLICATION_APPROVAL_REQUIRED

    allowed = _decide(
        ExternalAction.PUBLISH,
        mode=AutomationMode.ASSISTED,
        publication_approved=True,
    )
    assert allowed.allowed is True
    assert allowed.reason_code == REASON_ALLOWED


def test_manual_mode_never_automates_external_actions() -> None:
    decision = _decide(ExternalAction.BROWSER, mode=AutomationMode.MANUAL)
    assert decision.allowed is False
    assert decision.reason_code == REASON_MANUAL_MODE


def test_stop_external_actions_blocks_side_effects_and_keeps_safe_actions() -> None:
    stopped = OperationalState(stop_external_actions=True, updated_at=FIXED_NOW)
    for action in (
        ExternalAction.PUBLISH,
        ExternalAction.BROWSER,
        ExternalAction.AUTHENTICATED_LINK,
    ):
        decision = _decide(
            action, mode=AutomationMode.AUTO, state=stopped, publication_approved=True
        )
        assert decision.allowed is False, action
        assert decision.reason_code == REASON_STOP_EXTERNAL_ACTIONS, action

    for action in (ExternalAction.READ, ExternalAction.DIAGNOSTIC, ExternalAction.RECOVERY):
        decision = _decide(action, mode=AutomationMode.SHADOW, state=stopped)
        assert decision.allowed is True, action
        assert decision.reason_code == REASON_ALLOWED, action
        assert decision.external is False


def test_paused_draining_and_maintenance_block_new_side_effects() -> None:
    expected = {
        GlobalMode.PAUSED: REASON_GLOBAL_MODE_PAUSED,
        GlobalMode.DRAINING: REASON_GLOBAL_MODE_DRAINING,
        GlobalMode.MAINTENANCE: REASON_GLOBAL_MODE_MAINTENANCE,
    }
    for mode, reason in expected.items():
        decision = _decide(
            ExternalAction.PUBLISH,
            mode=AutomationMode.AUTO,
            state=OperationalState(global_mode=mode, updated_at=FIXED_NOW),
            publication_approved=True,
        )
        assert decision.allowed is False, mode
        assert decision.reason_code == reason, mode

    # Safe work already allowed keeps running under DRAINING.
    safe = _decide(
        ExternalAction.RECOVERY,
        mode=AutomationMode.AUTO,
        state=OperationalState(global_mode=GlobalMode.DRAINING, updated_at=FIXED_NOW),
    )
    assert safe.allowed is True


def test_compliance_is_blocking_and_never_released_by_human_approval() -> None:
    cases = {
        "UNKNOWN": REASON_POLICY_UNKNOWN,
        "BLOCKED": REASON_POLICY_BLOCK,
        "REVIEW_REQUIRED": REASON_POLICY_REVIEW_REQUIRED,
    }
    for status, reason in cases.items():
        compliance = build_compliance_policy(
            {"schema_version": "1.0", "policy_version": "c1", "status": status}
        )
        decision = _decide(
            ExternalAction.PUBLISH,
            mode=AutomationMode.AUTO,
            compliance=compliance,
            publication_approved=True,
        )
        assert decision.allowed is False, status
        assert decision.reason_code == reason, status

    expired = _active_compliance(review_due_at=(FIXED_NOW - timedelta(days=1)).isoformat())
    expired_decision = _decide(
        ExternalAction.PUBLISH,
        mode=AutomationMode.AUTO,
        compliance=expired,
        publication_approved=True,
    )
    assert expired_decision.allowed is False
    assert expired_decision.reason_code == REASON_POLICY_EXPIRED

    not_effective = _active_compliance(effective_from=(FIXED_NOW + timedelta(days=1)).isoformat())
    not_effective_decision = _decide(
        ExternalAction.PUBLISH,
        mode=AutomationMode.AUTO,
        compliance=not_effective,
        publication_approved=True,
    )
    assert not_effective_decision.allowed is False
    assert not_effective_decision.reason_code == REASON_POLICY_NOT_EFFECTIVE


def test_integration_failure_isolates_scope() -> None:
    telegram_down = _decide(
        ExternalAction.PUBLISH,
        mode=AutomationMode.AUTO,
        integration="telegram",
        integration_state=IntegrationState.OFFLINE,
        publication_approved=True,
    )
    assert telegram_down.allowed is False
    assert telegram_down.reason_code == REASON_INTEGRATION_UNAVAILABLE

    whatsapp_up = _decide(
        ExternalAction.PUBLISH,
        mode=AutomationMode.AUTO,
        integration="whatsapp",
        integration_state=IntegrationState.ONLINE,
        publication_approved=True,
    )
    assert whatsapp_up.allowed is True

    # An integration without a registered state fails closed.
    unknown = _decide(
        ExternalAction.PUBLISH,
        mode=AutomationMode.AUTO,
        integration="telegram",
        publication_approved=True,
    )
    assert unknown.allowed is False
    assert unknown.reason_code == REASON_INTEGRATION_UNAVAILABLE

    # Safe reading is never isolated by an unhealthy integration.
    read = _decide(
        ExternalAction.READ,
        mode=AutomationMode.AUTO,
        integration="telegram",
        integration_state=IntegrationState.OFFLINE,
    )
    assert read.allowed is True


def test_most_specific_rule_resolves_the_mode() -> None:
    policy = build_automation_policy(
        {
            "schema_version": "1.0",
            "policy_version": "a1",
            "default_mode": "SHADOW",
            "rules": [
                {"mode": "ASSISTED", "channel": "TELEGRAM"},
                {"mode": "AUTO", "channel": "TELEGRAM", "brand": "RADAR_BEAUTY"},
            ],
        }
    )
    assert policy.mode_for(channel="TELEGRAM") is AutomationMode.ASSISTED
    assert policy.mode_for(channel="TELEGRAM", brand=Brand.RADAR_BEAUTY) is AutomationMode.AUTO
    assert policy.mode_for(channel="WHATSAPP") is AutomationMode.SHADOW


def test_policies_are_versioned_and_hashed() -> None:
    first = build_automation_policy(
        {"schema_version": "1.0", "policy_version": "a1", "default_mode": "SHADOW"}
    )
    same = build_automation_policy(
        {"schema_version": "1.0", "policy_version": "a1", "default_mode": "SHADOW"}
    )
    other = build_automation_policy(
        {"schema_version": "1.0", "policy_version": "a1", "default_mode": "ASSISTED"}
    )
    assert first.content_hash == same.content_hash
    assert first.content_hash != other.content_hash

    compliance = _active_compliance()
    assert compliance.content_hash
    assert compliance.policy_version == "c1"
    assert compliance.blocking_reason(FIXED_NOW) is None


def test_invalid_policies_and_inputs_fail_closed() -> None:
    with pytest.raises(OperationsError) as automation_error:
        build_automation_policy({"schema_version": "9.9", "policy_version": "a1"})
    assert automation_error.value.error.code == AUTOMATION_POLICY_INVALID

    with pytest.raises(OperationsError) as missing_version:
        build_automation_policy({"schema_version": "1.0"})
    assert missing_version.value.error.code == AUTOMATION_POLICY_INVALID

    with pytest.raises(OperationsError) as bad_mode:
        build_automation_policy(
            {"schema_version": "1.0", "policy_version": "a1", "default_mode": "TURBO"}
        )
    assert bad_mode.value.error.code == AUTOMATION_POLICY_INVALID

    with pytest.raises(OperationsError) as matcherless_rule:
        build_automation_policy(
            {
                "schema_version": "1.0",
                "policy_version": "a1",
                "rules": [{"mode": "AUTO"}],
            }
        )
    assert matcherless_rule.value.error.code == AUTOMATION_POLICY_INVALID

    with pytest.raises(OperationsError) as compliance_status:
        build_compliance_policy(
            {"schema_version": "1.0", "policy_version": "c1", "status": "TURBO"}
        )
    assert compliance_status.value.error.code == COMPLIANCE_POLICY_INVALID

    with pytest.raises(OperationsError) as compliance_time:
        build_compliance_policy(
            {"schema_version": "1.0", "policy_version": "c1", "review_due_at": "not-a-date"}
        )
    assert compliance_time.value.error.code == COMPLIANCE_POLICY_INVALID

    assert OPERATIONS_INPUT_INVALID == "RAD-WF-018"
