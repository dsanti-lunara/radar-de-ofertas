from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from radar.domain.evaluation import (
    BASE_HARD_RULE_CHECKS,
    CONFIDENCE_SCORING_VERSION,
    DEAL_SCORING_VERSION,
    EVALUATION_INPUT_INVALID,
    EVALUATION_SCORING_VERSION,
    MONETIZATION_SCORING_VERSION,
    WARNING_CONVERSION_EVIDENCE_NEUTRAL,
    WARNING_DEAL_COMPONENT_MISSING,
    WEIGHT_BRAND_FIT,
    WEIGHT_COMPLETENESS,
    WEIGHT_CONVERSION_EVIDENCE,
    WEIGHT_CROSS_VALIDATION,
    WEIGHT_DEMAND,
    WEIGHT_EFFECTIVE_COMMISSION_PERCENT,
    WEIGHT_ESTIMATED_COMMISSION,
    WEIGHT_EXTRA_COMMISSION,
    WEIGHT_FRESHNESS,
    WEIGHT_PRICE_HISTORY_DEPTH,
    WEIGHT_PRICE_OPPORTUNITY,
    WEIGHT_SELLER_QUALITY,
    WEIGHT_SOURCE_RELIABILITY,
    ConfidenceFacts,
    ConfidenceLevel,
    DealFacts,
    Decision,
    EvaluationError,
    HardRule,
    MonetizationFacts,
    build_evaluation,
    compute_confidence,
    compute_deal_score,
    compute_monetization_score,
    confidence_level_for,
    decide,
)
from radar.domain.taxonomy import Brand, HardRuleViolation

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _evaluation(
    *,
    deal: DealFacts | None = None,
    monetization: MonetizationFacts | None = None,
    confidence: ConfidenceFacts | None = None,
    declared_hard_rules=(),
    classification_hard_rules=(),
):
    return build_evaluation(
        evaluation_id="eval_1",
        candidate_id="cand_1",
        brand=Brand.RADAR_BEAUTY,
        deal=deal
        or DealFacts(price_opportunity=100, seller_quality=100, demand=100, brand_fit=100),
        monetization=monetization,
        confidence=confidence
        or ConfidenceFacts(
            source_reliability=100,
            freshness=100,
            completeness=100,
            price_history_depth=100,
            cross_validation=100,
        ),
        declared_hard_rules=declared_hard_rules,
        classification_hard_rules=classification_hard_rules,
        correlation_id="cid-1",
        created_at=_NOW,
        audit_event_id="aud_1",
    )


def test_deal_weights_follow_sdd() -> None:
    result = compute_deal_score(
        candidate_id="cand_1",
        facts=DealFacts(price_opportunity=80, seller_quality=60, demand=100, brand_fit=60),
    )

    assert (WEIGHT_PRICE_OPPORTUNITY, WEIGHT_SELLER_QUALITY, WEIGHT_DEMAND, WEIGHT_BRAND_FIT) == (
        40,
        25,
        20,
        15,
    )
    weights = {component.name: component.weight for component in result.components}
    assert weights == {
        "price_opportunity": 40,
        "seller_quality": 25,
        "demand": 20,
        "brand_fit": 15,
    }
    # 40*80 + 25*60 + 20*100 + 15*60 = 7600 -> 76.00
    assert result.score == Decimal("76.00")


def test_deal_score_stays_on_the_zero_to_hundred_scale() -> None:
    result = compute_deal_score(
        candidate_id="cand_1",
        facts=DealFacts(price_opportunity=100, seller_quality=100, demand=100, brand_fit=100),
    )
    assert result.score == Decimal("100.00")
    assert all(
        component.score is not None and 0 <= component.score <= 100
        for component in result.components
    )


def test_missing_required_deal_component_is_blocking() -> None:
    result = compute_deal_score(
        candidate_id="cand_1",
        facts=DealFacts(price_opportunity=100, seller_quality=None, demand=100, brand_fit=100),
    )

    assert result.score is None
    assert result.score != Decimal(0)
    assert result.missing == ("seller_quality",)
    assert WARNING_DEAL_COMPONENT_MISSING in [warning.code for warning in result.warnings]

    evaluation = _evaluation(
        deal=DealFacts(price_opportunity=100, seller_quality=None, demand=100, brand_fit=100)
    )
    assert evaluation.decision is Decision.REJECT
    assert "INSUFFICIENT_REQUIRED_DATA" in [rule.rule for rule in evaluation.failed_rules]
    assert evaluation.auto_eligible is False


def test_invalid_component_score_raises_structured_error() -> None:
    with pytest.raises(EvaluationError) as excinfo:
        compute_deal_score(
            candidate_id="cand_1",
            facts=DealFacts(price_opportunity=101, seller_quality=100, demand=100, brand_fit=100),
        )
    assert excinfo.value.error.code == EVALUATION_INPUT_INVALID
    assert excinfo.value.error.retryable is False


def test_decision_matrix_boundaries() -> None:
    # <60 rejects regardless of confidence.
    assert (
        decide(
            deal_score=Decimal("59.99"),
            confidence=ConfidenceLevel.HIGH,
            failed_rules=(),
        )
        is Decision.REJECT
    )
    # 60..79.99 rejects on LOW and reviews otherwise.
    assert (
        decide(deal_score=Decimal("60"), confidence=ConfidenceLevel.LOW, failed_rules=())
        is Decision.REJECT
    )
    assert (
        decide(deal_score=Decimal("60"), confidence=ConfidenceLevel.MEDIUM, failed_rules=())
        is Decision.REVIEW
    )
    assert (
        decide(deal_score=Decimal("79.99"), confidence=ConfidenceLevel.HIGH, failed_rules=())
        is Decision.REVIEW
    )
    # >=80 reviews on LOW and approves on MEDIUM/HIGH.
    assert (
        decide(deal_score=Decimal("80"), confidence=ConfidenceLevel.LOW, failed_rules=())
        is Decision.REVIEW
    )
    assert (
        decide(deal_score=Decimal("80"), confidence=ConfidenceLevel.MEDIUM, failed_rules=())
        is Decision.APPROVE
    )
    assert (
        decide(deal_score=Decimal("80"), confidence=ConfidenceLevel.HIGH, failed_rules=())
        is Decision.APPROVE
    )


def test_confidence_bands_follow_sdd() -> None:
    assert confidence_level_for(None) is None
    assert confidence_level_for(0) is ConfidenceLevel.LOW
    assert confidence_level_for(49) is ConfidenceLevel.LOW
    assert confidence_level_for(50) is ConfidenceLevel.MEDIUM
    assert confidence_level_for(79) is ConfidenceLevel.MEDIUM
    assert confidence_level_for(80) is ConfidenceLevel.HIGH
    assert confidence_level_for(100) is ConfidenceLevel.HIGH


def test_confidence_weights_follow_sdd() -> None:
    result = compute_confidence(
        candidate_id="cand_1",
        facts=ConfidenceFacts(
            source_reliability=100,
            freshness=100,
            completeness=100,
            price_history_depth=100,
            cross_validation=100,
        ),
    )
    assert (
        WEIGHT_SOURCE_RELIABILITY,
        WEIGHT_FRESHNESS,
        WEIGHT_COMPLETENESS,
        WEIGHT_PRICE_HISTORY_DEPTH,
        WEIGHT_CROSS_VALIDATION,
    ) == (30, 25, 20, 15, 10)
    assert result.score == 100
    assert result.level is ConfidenceLevel.HIGH
    # Missing components are explicit gaps, never invented zeros.
    partial = compute_confidence(
        candidate_id="cand_1",
        facts=ConfidenceFacts(source_reliability=100),
    )
    assert partial.score == 100
    assert partial.weight_covered == 30
    assert partial.fully_calibrated is False


def test_hard_rules_precede_scores_and_ai() -> None:
    evaluation = _evaluation(declared_hard_rules=(HardRule.COMPLIANCE_BLOCK,))

    assert evaluation.deal_score == Decimal("100.00")
    assert evaluation.confidence is ConfidenceLevel.HIGH
    assert evaluation.decision is Decision.REJECT
    assert evaluation.auto_eligible is False
    assert "COMPLIANCE_BLOCK" in [rule.rule for rule in evaluation.failed_rules]


def test_out_of_scope_category_hard_rule_is_propagated() -> None:
    evaluation = _evaluation(
        classification_hard_rules=(
            HardRuleViolation(
                rule="OUT_OF_SCOPE_CATEGORY",
                message="Categoria fora do escopo da marca",
                context={"brand": "CASA_EM_ORDEM"},
            ),
        )
    )

    assert evaluation.decision is Decision.REJECT
    assert "OUT_OF_SCOPE_CATEGORY" in [rule.rule for rule in evaluation.failed_rules]
    assert "INSUFFICIENT_REQUIRED_DATA" in evaluation.passed_rules


def test_deal_45_with_monetization_97_stays_rejected() -> None:
    monetization = MonetizationFacts(
        estimated_commission=97,
        effective_commission_percent=97,
        conversion_evidence=97,
        extra_commission=97,
    )
    evaluation = _evaluation(
        deal=DealFacts(price_opportunity=45, seller_quality=45, demand=45, brand_fit=45),
        monetization=monetization,
    )

    assert evaluation.deal_score == Decimal("45.00")
    assert evaluation.monetization_score == 97
    assert evaluation.decision is Decision.REJECT
    # Monetization is not an input to the matrix, so it cannot elevate a rejection.
    assert (
        decide(deal_score=Decimal("45.00"), confidence=ConfidenceLevel.HIGH, failed_rules=())
        is Decision.REJECT
    )


def test_commission_never_changes_the_deal_score() -> None:
    low = _evaluation(
        deal=DealFacts(price_opportunity=80, seller_quality=70, demand=60, brand_fit=50),
        monetization=MonetizationFacts(estimated_commission=0),
    )
    high = _evaluation(
        deal=DealFacts(price_opportunity=80, seller_quality=70, demand=60, brand_fit=50),
        monetization=MonetizationFacts(
            estimated_commission=100,
            effective_commission_percent=100,
            conversion_evidence=100,
            extra_commission=100,
        ),
    )

    assert low.deal_score == high.deal_score
    assert low.decision is high.decision


def test_monetization_weights_and_neutral_conversion() -> None:
    result = compute_monetization_score(
        candidate_id="cand_1",
        facts=MonetizationFacts(
            estimated_commission=100,
            effective_commission_percent=100,
            conversion_evidence=100,
            extra_commission=100,
        ),
    )
    assert (
        WEIGHT_ESTIMATED_COMMISSION,
        WEIGHT_EFFECTIVE_COMMISSION_PERCENT,
        WEIGHT_CONVERSION_EVIDENCE,
        WEIGHT_EXTRA_COMMISSION,
    ) == (40, 25, 20, 15)
    assert result.score == 100
    assert result.fully_calibrated is True

    neutral = compute_monetization_score(candidate_id="cand_1", facts=MonetizationFacts())
    assert neutral.score == 50
    assert WARNING_CONVERSION_EVIDENCE_NEUTRAL in [warning.code for warning in neutral.warnings]
    assert neutral.fully_calibrated is False


def test_evaluation_snapshot_and_breakdown_are_versioned() -> None:
    evaluation = _evaluation(
        deal=DealFacts(price_opportunity=90, seller_quality=80, demand=70, brand_fit=60)
    )

    assert evaluation.scoring_version == EVALUATION_SCORING_VERSION
    assert evaluation.deal_scoring_version == DEAL_SCORING_VERSION
    assert evaluation.monetization_scoring_version == MONETIZATION_SCORING_VERSION
    assert evaluation.confidence_scoring_version == CONFIDENCE_SCORING_VERSION

    contract = evaluation.to_contract()
    # 40*90 + 25*80 + 20*70 + 15*60 = 7900 -> 79.00
    assert contract["deal_score"] == "79.00"
    assert contract["breakdown"]["deal"]["scoring_version"] == DEAL_SCORING_VERSION
    assert contract["feature_snapshot"]["deal"] == {
        "price_opportunity": 90,
        "seller_quality": 80,
        "demand": 70,
        "brand_fit": 60,
    }
    assert contract["passed_rules"] == list(BASE_HARD_RULE_CHECKS)


def test_auto_eligible_requires_high_confidence_and_no_hard_rules() -> None:
    approved = _evaluation()
    assert approved.decision is Decision.APPROVE
    assert approved.auto_eligible is True

    medium = _evaluation(
        confidence=ConfidenceFacts(
            source_reliability=60,
            freshness=60,
            completeness=60,
            price_history_depth=60,
            cross_validation=60,
        )
    )
    assert medium.decision is Decision.APPROVE
    assert medium.confidence is ConfidenceLevel.MEDIUM
    assert medium.auto_eligible is False
