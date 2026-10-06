from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from radar.domain.price_opportunity import Coupon, CouponState
from radar.domain.purchase_source import (
    APPROVED_PURCHASE_SOURCE_POLICY,
    PURCHASE_SOURCE_INPUT_INVALID,
    PURCHASE_SOURCE_SCHEMA_VERSION,
    WARNING_COMMISSION_IGNORED,
    WARNING_CONDITIONS_NOT_COMPARABLE,
    WARNING_MATERIAL_DIFFERENCE,
    WARNING_NO_RELIABLE_COMPARISON,
    WARNING_NOT_EQUIVALENT,
    WARNING_PRODUCT_NOT_IDENTIFIED,
    WARNING_UNRELIABLE_PRICE,
    MaterialDifferenceAction,
    PurchaseSource,
    PurchaseSourceDecision,
    PurchaseSourceError,
    PurchaseSourcePolicy,
    PurchaseSourcePolicyInvalidError,
    build_purchase_source_evidence,
    build_purchase_source_policy,
    compute_purchase_source,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _policy(
    *,
    threshold: str = "8",
    action: MaterialDifferenceAction = MaterialDifferenceAction.REVIEW,
) -> PurchaseSourcePolicy:
    return PurchaseSourcePolicy(
        policy_version="policy-test",
        content_hash="hash-test",
        reference_difference_percent=Decimal(threshold),
        on_material_difference=action,
    )


def _chosen(**overrides: object) -> PurchaseSource:
    data: dict[str, object] = {
        "source_id": "candidate:cand_1",
        "price": Decimal("100"),
        "marketplace": "MERCADO_LIVRE",
        "shipping_cost": Decimal("0"),
        "product_equivalence_id": "product-1",
    }
    data.update(overrides)
    return PurchaseSource(**data)  # type: ignore[arg-type]


def _alternative(**overrides: object) -> PurchaseSource:
    data: dict[str, object] = {
        "source_id": "shopee:1",
        "price": Decimal("100"),
        "marketplace": "SHOPEE",
        "shipping_cost": Decimal("0"),
        "product_equivalence_id": "product-1",
    }
    data.update(overrides)
    return PurchaseSource(**data)  # type: ignore[arg-type]


def _compute(
    *,
    chosen: PurchaseSource,
    alternatives: list[PurchaseSource],
    policy: PurchaseSourcePolicy | None = None,
):
    return compute_purchase_source(
        candidate_id="cand_1",
        chosen=chosen,
        alternatives=alternatives,
        policy=policy or _policy(),
        as_of=NOW,
    )


def test_reference_above_8_percent_goes_to_review() -> None:
    result = _compute(
        chosen=_chosen(price=Decimal("109")),
        alternatives=[_alternative(price=Decimal("100"))],
    )

    assert result.difference_percent == Decimal("9.0000")
    assert result.material is True
    assert result.decision is PurchaseSourceDecision.REVIEW
    assert result.substituted_source_id is None
    assert result.commission_considered is False
    assert any(warning.code == WARNING_MATERIAL_DIFFERENCE for warning in result.warnings)


def test_exactly_8_percent_is_not_material() -> None:
    result = _compute(
        chosen=_chosen(price=Decimal("108")),
        alternatives=[_alternative(price=Decimal("100"))],
    )

    assert result.difference_percent == Decimal("8.0000")
    assert result.material is False
    assert result.decision is PurchaseSourceDecision.KEEP


def test_substitute_action_replaces_the_source() -> None:
    result = _compute(
        chosen=_chosen(price=Decimal("109")),
        alternatives=[_alternative(price=Decimal("100"))],
        policy=_policy(action=MaterialDifferenceAction.SUBSTITUTE),
    )

    assert result.decision is PurchaseSourceDecision.SUBSTITUTE
    assert result.substituted_source_id == "shopee:1"
    assert result.best_alternative_source_id == "shopee:1"


def test_cheapest_eligible_alternative_is_selected() -> None:
    result = _compute(
        chosen=_chosen(price=Decimal("130")),
        alternatives=[
            _alternative(source_id="shopee:2", price=Decimal("100")),
            _alternative(source_id="shopee:1", price=Decimal("95")),
        ],
        policy=_policy(action=MaterialDifferenceAction.SUBSTITUTE),
    )

    assert result.best_alternative_source_id == "shopee:1"
    assert result.substituted_source_id == "shopee:1"


def test_confirmed_coupon_reduces_effective_price() -> None:
    chosen = _chosen(
        price=Decimal("103"),
        coupon=Coupon(state=CouponState.CONFIRMED, amount=Decimal("3")),
    )
    result = _compute(chosen=chosen, alternatives=[_alternative(price=Decimal("100"))])

    assert result.chosen_effective_price == Decimal("100")
    assert result.difference_percent == Decimal("0.0000")
    assert result.decision is PurchaseSourceDecision.KEEP


def test_unconfirmed_coupon_never_reduces_effective_price() -> None:
    chosen = _chosen(
        price=Decimal("100"),
        coupon=Coupon(state=CouponState.LIKELY, amount=Decimal("50")),
    )
    result = _compute(chosen=chosen, alternatives=[_alternative(price=Decimal("85"))])

    chosen_evaluation = next(source for source in result.sources if source.role == "chosen")
    assert chosen_evaluation.effective_price == Decimal("100")
    assert result.difference_percent == Decimal("17.6471")
    assert result.decision is PurchaseSourceDecision.REVIEW


def test_unknown_shipping_excludes_the_source() -> None:
    result = _compute(
        chosen=_chosen(shipping_cost=None),
        alternatives=[_alternative(price=Decimal("10"))],
    )

    assert result.chosen_effective_price is None
    assert result.material is False
    assert any(warning.code == WARNING_NO_RELIABLE_COMPARISON for warning in result.warnings)


def test_alternative_without_known_shipping_is_unreliable() -> None:
    result = _compute(
        chosen=_chosen(price=Decimal("110")),
        alternatives=[_alternative(price=Decimal("10"), shipping_cost=None)],
    )

    assert any(warning.code == WARNING_UNRELIABLE_PRICE for warning in result.warnings)
    assert result.decision is PurchaseSourceDecision.KEEP


def test_non_equivalent_product_is_not_a_valid_comparison() -> None:
    result = _compute(
        chosen=_chosen(price=Decimal("200")),
        alternatives=[_alternative(price=Decimal("50"), product_equivalence_id="other-product")],
    )

    assert any(warning.code == WARNING_NOT_EQUIVALENT for warning in result.warnings)
    assert result.decision is PurchaseSourceDecision.KEEP
    assert result.difference_percent is None


def test_unidentified_product_has_no_valid_comparison() -> None:
    result = _compute(
        chosen=_chosen(price=Decimal("200"), product_equivalence_id=None),
        alternatives=[_alternative(price=Decimal("50"), product_equivalence_id=None)],
    )

    assert any(warning.code == WARNING_PRODUCT_NOT_IDENTIFIED for warning in result.warnings)
    assert any(warning.code == WARNING_NO_RELIABLE_COMPARISON for warning in result.warnings)
    assert result.decision is PurchaseSourceDecision.KEEP


def test_different_conditions_are_not_comparable() -> None:
    result = _compute(
        chosen=_chosen(conditions={"variant": "100ml"}),
        alternatives=[
            _alternative(price=Decimal("50"), conditions={"variant": "200ml"}),
        ],
    )

    assert any(warning.code == WARNING_CONDITIONS_NOT_COMPARABLE for warning in result.warnings)
    assert result.decision is PurchaseSourceDecision.KEEP


def test_commission_never_changes_the_decision() -> None:
    alternatives = [_alternative(price=Decimal("100"))]
    low = _compute(
        chosen=_chosen(price=Decimal("109"), affiliate_commission=Decimal("0")),
        alternatives=alternatives,
    )
    high = _compute(
        chosen=_chosen(price=Decimal("109"), affiliate_commission=Decimal("100000")),
        alternatives=alternatives,
    )

    assert low.decision is high.decision is PurchaseSourceDecision.REVIEW
    assert low.difference_percent == high.difference_percent
    assert low.commission_considered is False
    assert high.commission_considered is False
    assert any(warning.code == WARNING_COMMISSION_IGNORED for warning in high.warnings)


def test_duplicate_source_id_is_rejected() -> None:
    with pytest.raises(PurchaseSourceError) as excinfo:
        _compute(
            chosen=_chosen(source_id="duplicate"),
            alternatives=[_alternative(source_id="duplicate", price=Decimal("1"))],
        )

    assert excinfo.value.error.code == PURCHASE_SOURCE_INPUT_INVALID


def test_non_positive_price_is_rejected() -> None:
    with pytest.raises(PurchaseSourceError):
        _compute(chosen=_chosen(price=Decimal("0")), alternatives=[])


def test_evidence_captures_the_decision_facts() -> None:
    result = _compute(
        chosen=_chosen(price=Decimal("109")),
        alternatives=[_alternative(price=Decimal("100"))],
    )
    evidence = build_purchase_source_evidence(
        decision_id="psd_1",
        result=result,
        captured_at=NOW,
        make_id=lambda prefix: f"{prefix}_1",
    )

    fields = {item.field_name: item.value for item in evidence}
    assert fields["decision"] == "REVIEW"
    assert fields["difference_percent"] == "9.0000"
    assert fields["chosen_effective_price"] == "109"
    assert fields["alternative_effective_price"] == "100"
    assert all(item.entity_id == "psd_1" for item in evidence)


def test_result_contract_is_versioned() -> None:
    result = _compute(chosen=_chosen(), alternatives=[])
    contract = result.to_contract()

    assert contract["schema_version"] == PURCHASE_SOURCE_SCHEMA_VERSION
    assert contract["status"] == "DECIDED"
    assert contract["commission_considered"] is False
    assert contract["policy"]["reference_difference_percent"] == "8"


def test_default_policy_uses_frozen_threshold_and_review() -> None:
    assert APPROVED_PURCHASE_SOURCE_POLICY.reference_difference_percent == Decimal("8")
    assert APPROVED_PURCHASE_SOURCE_POLICY.on_material_difference is MaterialDifferenceAction.REVIEW


def test_policy_builder_rejects_invalid_action_and_threshold() -> None:
    with pytest.raises(PurchaseSourcePolicyInvalidError) as excinfo:
        build_purchase_source_policy({"policy_version": "p", "on_material_difference": "AUTO"})
    assert excinfo.value.error.code == "RAD-CFG-008"

    with pytest.raises(PurchaseSourcePolicyInvalidError):
        build_purchase_source_policy({"policy_version": "p", "reference_difference_percent": "-1"})

    with pytest.raises(PurchaseSourcePolicyInvalidError):
        build_purchase_source_policy({"policy_version": ""})
