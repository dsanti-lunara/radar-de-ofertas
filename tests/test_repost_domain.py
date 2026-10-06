from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from radar.domain.price_opportunity import Coupon, CouponState
from radar.domain.repost import (
    APPROVED_REPOST_POLICY,
    APPROVED_REPOST_POLICY_DOCUMENT,
    EVIDENCE_FIELD_MATERIAL_CHANGE,
    MaterialChangeType,
    PublicationSnapshot,
    RepostError,
    RepostEvidence,
    RepostEvidenceType,
    RepostFacts,
    RepostOutcome,
    RepostPolicyInvalidError,
    RepostReason,
    RepostWarning,
    build_repost_evidence,
    build_repost_policy,
    compute_repost,
    repost_input_invalid_error,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _policy(**overrides: object):
    document = dict(APPROVED_REPOST_POLICY_DOCUMENT)
    document.update(overrides)
    return build_repost_policy(document)


def _published(
    *,
    hours_ago: float = 10,
    price: str = "100",
    coupon: Coupon | None = None,
    conditions: dict[str, str] | None = None,
) -> PublicationSnapshot:
    return PublicationSnapshot(
        published_at=NOW - timedelta(hours=hours_ago),
        price=Decimal(price),
        publication_id="pub-1",
        coupon=coupon if coupon is not None else Coupon(state=CouponState.NOT_APPLICABLE),
        conditions=conditions or {},
    )


def _coupon_evidence() -> RepostEvidence:
    return RepostEvidence(
        evidence_type=RepostEvidenceType.COUPON,
        reference_id="rc-1",
        field="coupon",
        value="SAVE10",
    )


def _condition_evidence() -> RepostEvidence:
    return RepostEvidence(
        evidence_type=RepostEvidenceType.CONDITION,
        reference_id="rc-2",
        field="conditions",
        value="variant=12L",
    )


def test_approved_policy_follows_sdd_reference() -> None:
    assert APPROVED_REPOST_POLICY.cooldown_hours == 72
    assert APPROVED_REPOST_POLICY.price_drop_percent == Decimal("10")
    assert APPROVED_REPOST_POLICY.strong_deal_threshold == Decimal("80")
    assert APPROVED_REPOST_POLICY.content_hash


def test_first_publication_is_allowed_without_history() -> None:
    result = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(current_price=Decimal("100")),
        publication_history=[],
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )

    assert result.decision is RepostOutcome.ALLOWED
    assert result.reason is RepostReason.FIRST_PUBLICATION
    assert result.publication is None
    assert result.cooldown_expires_at is None


def test_price_drop_at_or_above_ten_percent_releases_repost() -> None:
    result = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(current_price=Decimal("90")),
        publication_history=[_published(price="100")],
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )

    assert result.decision is RepostOutcome.ALLOWED
    assert result.reason is RepostReason.MATERIAL_PRICE_DROP
    assert result.observed_price_drop_percent == Decimal("10.00")
    assert result.material_changes[0].change_type is MaterialChangeType.PRICE_DROP


def test_price_drop_below_ten_percent_is_not_material() -> None:
    result = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(current_price=Decimal("90.01")),
        publication_history=[_published(price="100")],
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )

    assert result.decision is RepostOutcome.BLOCKED
    assert result.reason is RepostReason.DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE
    assert result.observed_price_drop_percent == Decimal("9.99")


def test_irrelevant_change_with_active_cooldown_blocks_repost() -> None:
    result = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(current_price=Decimal("99.50"), deal_score=Decimal("95")),
        publication_history=[_published(hours_ago=10, price="100")],
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )

    assert result.decision is RepostOutcome.BLOCKED
    assert result.reason is RepostReason.DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE
    assert result.allowed is False
    assert result.cooldown_expired is False
    assert any(
        warning.code == "DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE" for warning in result.warnings
    )


def test_cooldown_expired_without_material_change_requires_strong_deal() -> None:
    history = [_published(hours_ago=80, price="100")]

    strong = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(current_price=Decimal("99.50"), deal_score=Decimal("80")),
        publication_history=history,
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )
    weak = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(current_price=Decimal("99.50"), deal_score=Decimal("79.99")),
        publication_history=history,
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )

    assert strong.decision is RepostOutcome.ALLOWED
    assert strong.reason is RepostReason.COOLDOWN_EXPIRED_STRONG_DEAL
    assert strong.cooldown_expired is True
    assert weak.decision is RepostOutcome.BLOCKED
    assert weak.reason is RepostReason.DEAL_NOT_STRONG
    assert any(warning.code == "REPOST_DEAL_NOT_STRONG" for warning in weak.warnings)


def test_material_coupon_requires_evidence() -> None:
    coupon = Coupon(state=CouponState.CONFIRMED, amount=Decimal("10"), code="SAVE10")
    history = [_published(price="100", coupon=Coupon(state=CouponState.NOT_APPLICABLE))]

    without = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(current_price=Decimal("100"), coupon=coupon),
        publication_history=history,
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )
    with_evidence = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(
            current_price=Decimal("100"), coupon=coupon, evidence=(_coupon_evidence(),)
        ),
        publication_history=history,
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )

    assert without.decision is RepostOutcome.BLOCKED
    assert any(warning.code == "REPOST_COUPON_WITHOUT_EVIDENCE" for warning in without.warnings)
    assert with_evidence.decision is RepostOutcome.ALLOWED
    assert with_evidence.reason is RepostReason.MATERIAL_COUPON
    assert with_evidence.material_changes[0].change_type is MaterialChangeType.COUPON


def test_material_condition_requires_evidence() -> None:
    history = [_published(price="100", conditions={"variant": "500ml"})]

    without = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(current_price=Decimal("100"), conditions={"variant": "12L"}),
        publication_history=history,
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )
    with_evidence = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(
            current_price=Decimal("100"),
            conditions={"variant": "12L"},
            evidence=(_condition_evidence(),),
        ),
        publication_history=history,
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )

    assert without.decision is RepostOutcome.BLOCKED
    assert any(warning.code == "REPOST_CONDITION_WITHOUT_EVIDENCE" for warning in without.warnings)
    assert with_evidence.decision is RepostOutcome.ALLOWED
    assert with_evidence.reason is RepostReason.MATERIAL_CONDITION


def test_unconfirmed_coupon_is_never_material() -> None:
    result = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(
            current_price=Decimal("100"),
            coupon=Coupon(state=CouponState.LIKELY, amount=Decimal("30")),
            evidence=(_coupon_evidence(),),
        ),
        publication_history=[_published(price="100")],
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )

    assert result.decision is RepostOutcome.BLOCKED
    assert any(warning.code == "REPOST_COUPON_NOT_CONFIRMED" for warning in result.warnings)


def test_non_positive_current_price_is_invalid() -> None:
    with pytest.raises(RepostError) as excinfo:
        compute_repost(
            candidate_id="cand-1",
            facts=RepostFacts(current_price=Decimal("0")),
            publication_history=[],
            policy=APPROVED_REPOST_POLICY,
            as_of=NOW,
        )
    assert repost_input_invalid_error("x").error.code == "RAD-CAP-015"
    assert excinfo.value.error.code == "RAD-CAP-015"


def test_build_repost_evidence_records_decision_and_material_change() -> None:
    result = compute_repost(
        candidate_id="cand-1",
        facts=RepostFacts(current_price=Decimal("90"), coupon=None, evidence=(_coupon_evidence(),)),
        publication_history=[_published(price="100")],
        policy=APPROVED_REPOST_POLICY,
        as_of=NOW,
    )
    ids = iter([f"evd-{index}" for index in range(50)])

    evidence = build_repost_evidence(
        decision_id="rpd-1",
        result=result,
        captured_at=NOW,
        make_id=lambda prefix: next(ids),
        supplied_evidence=(_coupon_evidence(),),
    )

    fields = {item.field_name for item in evidence}
    assert "decision" in fields
    assert "reason" in fields
    assert EVIDENCE_FIELD_MATERIAL_CHANGE in fields
    assert all(item.entity_id == "rpd-1" for item in evidence)


def test_policy_builder_rejects_invalid_documents() -> None:
    with pytest.raises(RepostPolicyInvalidError):
        build_repost_policy({"policy_version": ""})
    with pytest.raises(RepostPolicyInvalidError):
        build_repost_policy({"policy_version": "v", "cooldown_hours": 0})
    with pytest.raises(RepostPolicyInvalidError):
        build_repost_policy({"policy_version": "v", "cooldown_hours": 1.5})
    with pytest.raises(RepostPolicyInvalidError):
        build_repost_policy({"policy_version": "v", "price_drop_percent": 9.9})
    with pytest.raises(RepostPolicyInvalidError):
        build_repost_policy({"policy_version": "v", "strong_deal_threshold": 101})
    with pytest.raises(RepostPolicyInvalidError):
        build_repost_policy({"schema_version": "9.9", "policy_version": "v"})


def test_policy_is_versioned_and_hashed() -> None:
    first = _policy(price_drop_percent="10")
    second = _policy(price_drop_percent="10")
    changed = _policy(price_drop_percent="12")

    assert first.content_hash == second.content_hash
    assert first.content_hash != changed.content_hash
    assert first.to_contract()["price_drop_percent"] == "10"


def test_warning_contract_is_explicit() -> None:
    warning = RepostWarning(code="X", message="m", context={"a": 1})
    assert warning.to_contract() == {"code": "X", "message": "m", "context": {"a": 1}}
