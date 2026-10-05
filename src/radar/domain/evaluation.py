"""Immutable Candidate Evaluation: Deal, Monetization, Confidence and Decision.

This module implements the versioned, append-only *Evaluation* described in
``docs/03_DOMAIN_MODEL.md`` (RDR-016) and the Decision Engine of
``docs/05_SCORING_ENGINE.md`` (RDR-027, RDR-028, RDR-029, RDR-030). It composes
the deterministic components already produced by the dependent tickets
(Price Opportunity, Seller Quality, Demand and Brand Fit) into:

* a **Deal Score** on the ``0..100`` scale with the frozen macro weights
  ``Price 40% / Seller 25% / Demand 20% / Brand Fit 15%`` (AUT-046);
* a **Monetization Score** with the frozen weights
  ``commission 40% / effective % 25% / conversion evidence 20% / extra 15%``
  that can only order already acceptable opportunities and never approves a
  rejected one (AUT-051, AUT-052);
* a **Confidence** level computed independently of the Deal Score with the
  frozen weights ``source 30% / freshness 25% / completeness 20% / history 15% /
  cross validation 10%`` and the approved bands (AUT-054, AUT-055).

Two rules are load-bearing:

* **Hard Rules precede every score, AI step, link and publication** (AUT-056,
  invariant 4). A violated Hard Rule forces ``REJECT`` no matter how strong the
  scores are, and missing required Deal data is itself a blocking Hard Rule
  (``INSUFFICIENT_REQUIRED_DATA``), so an incomplete Candidate is never approved;
* **commission never enters the Deal Score** (AUT-051): the Deal facts carry no
  commission field and the Monetization result is only used for ordering. A low
  Deal Score stays rejected even with a Monetization Score of 97.

Every result carries the feature snapshot, the score breakdown and the scoring
versions it was computed from (AUT-030, AUT-065) so old evaluations are
immutable and traceable. The module is framework-free (no FastAPI/SQLAlchemy/
Chrome) so the domain stays independent from infrastructure (AUT-397), and it
never calls AI to compute a score (AUT-031).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from radar.domain.errors import RadarError, RadarException
from radar.domain.taxonomy import (
    HARD_RULE_OUT_OF_SCOPE_CATEGORY,
    Brand,
    HardRuleViolation,
)

#: Version of the public Evaluation contract.
EVALUATION_SCHEMA_VERSION = "1.0"

#: Version stored alongside the evaluation snapshot (AUT-065).
EVALUATION_SCORING_VERSION = "evaluation-1.0"
DEAL_SCORING_VERSION = "deal-1.0"
MONETIZATION_SCORING_VERSION = "monetization-1.0"
CONFIDENCE_SCORING_VERSION = "confidence-1.0"

#: Error code (see ``docs/ERROR_CATALOG.md``).
EVALUATION_INPUT_INVALID = "RAD-CAP-011"

#: Approved Deal Score macro weights, frozen by ``docs/05_SCORING_ENGINE.md``.
WEIGHT_PRICE_OPPORTUNITY = 40
WEIGHT_SELLER_QUALITY = 25
WEIGHT_DEMAND = 20
WEIGHT_BRAND_FIT = 15

#: Approved Monetization weights, frozen by ``docs/05_SCORING_ENGINE.md``.
WEIGHT_ESTIMATED_COMMISSION = 40
WEIGHT_EFFECTIVE_COMMISSION_PERCENT = 25
WEIGHT_CONVERSION_EVIDENCE = 20
WEIGHT_EXTRA_COMMISSION = 15

#: Approved Confidence weights, frozen by ``docs/05_SCORING_ENGINE.md``.
WEIGHT_SOURCE_RELIABILITY = 30
WEIGHT_FRESHNESS = 25
WEIGHT_COMPLETENESS = 20
WEIGHT_PRICE_HISTORY_DEPTH = 15
WEIGHT_CROSS_VALIDATION = 10

#: Decision thresholds (``docs/05_SCORING_ENGINE.md``).
DEAL_REJECT_BELOW = Decimal(60)
DEAL_STRONG_FROM = Decimal(80)

#: Confidence bands (``docs/05_SCORING_ENGINE.md``).
CONFIDENCE_MEDIUM_FROM = 50
CONFIDENCE_HIGH_FROM = 80

#: Neutral value approved for Conversion Evidence until own data exists.
NEUTRAL_CONVERSION_EVIDENCE = 50

#: Human-readable reasons attached to each component.
REASON_OK = "ok"
REASON_MISSING = "missing"
REASON_NEUTRAL = "neutral"

#: Soft Rule warnings emitted by the composition.
WARNING_DEAL_COMPONENT_MISSING = "DEAL_COMPONENT_MISSING"
WARNING_MONETIZATION_COMPONENT_MISSING = "MONETIZATION_COMPONENT_MISSING"
WARNING_CONVERSION_EVIDENCE_NEUTRAL = "CONVERSION_EVIDENCE_NEUTRAL"
WARNING_CONFIDENCE_COMPONENT_MISSING = "CONFIDENCE_COMPONENT_MISSING"

#: Blocking Hard Rules always checked by the Evaluation before any score or AI.
BASE_HARD_RULE_CHECKS: tuple[str, ...] = (
    "INSUFFICIENT_REQUIRED_DATA",
    HARD_RULE_OUT_OF_SCOPE_CATEGORY,
)


class Decision(StrEnum):
    """Decision matrix outcome (``docs/04_DATA_CONTRACTS.md``)."""

    REJECT = "REJECT"
    REVIEW = "REVIEW"
    APPROVE = "APPROVE"


class ConfidenceLevel(StrEnum):
    """Confidence bands (``docs/05_SCORING_ENGINE.md``)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class HardRule(StrEnum):
    """Hard Rules from ``docs/05_SCORING_ENGINE.md`` (AUT-056)."""

    OUT_OF_SCOPE_CATEGORY = HARD_RULE_OUT_OF_SCOPE_CATEGORY
    OUT_OF_STOCK = "OUT_OF_STOCK"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_URL = "INVALID_URL"
    BLACKLISTED_SELLER = "BLACKLISTED_SELLER"
    INVALID_AFFILIATE_DESTINATION = "INVALID_AFFILIATE_DESTINATION"
    INSUFFICIENT_REQUIRED_DATA = "INSUFFICIENT_REQUIRED_DATA"
    DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE = "DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE"
    COMPLIANCE_BLOCK = "COMPLIANCE_BLOCK"


class EvaluationError(RadarException):
    """Raised when an Evaluation request cannot be satisfied."""


def evaluation_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> EvaluationError:
    """Build the structured error for invalid Evaluation inputs."""

    return EvaluationError(
        RadarError(
            code=EVALUATION_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir os componentes da avaliação e consultar novamente",
            context=dict(context or {}),
        )
    )


@dataclass(frozen=True, slots=True)
class EvaluationWarning:
    """Explicit, non-fatal gap emitted by the composition."""

    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    """One explainable component of a score breakdown."""

    name: str
    weight: int
    score: int | None
    present: bool
    reason: str = REASON_OK

    def to_contract(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "weight": self.weight,
            "score": self.score,
            "present": self.present,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DealFacts:
    """Deal Score components produced by the dependent tickets.

    Each component is an already normalized ``0..100`` score or ``None`` when the
    dependent calculation reported an explicit calibration/data gap. There is no
    commission field here on purpose: commission never enters the Deal Score
    (AUT-051).
    """

    price_opportunity: int | None = None
    seller_quality: int | None = None
    demand: int | None = None
    brand_fit: int | None = None


@dataclass(frozen=True, slots=True)
class MonetizationFacts:
    """Monetization components (``docs/05_SCORING_ENGINE.md``)."""

    estimated_commission: int | None = None
    effective_commission_percent: int | None = None
    conversion_evidence: int | None = None
    extra_commission: int | None = None


@dataclass(frozen=True, slots=True)
class ConfidenceFacts:
    """Confidence components (``docs/05_SCORING_ENGINE.md``)."""

    source_reliability: int | None = None
    freshness: int | None = None
    completeness: int | None = None
    price_history_depth: int | None = None
    cross_validation: int | None = None


@dataclass(frozen=True, slots=True)
class DealScoreResult:
    """Deterministic Deal Score with its breakdown and blocking gaps."""

    candidate_id: str
    score: Decimal | None
    components: tuple[ScoreComponent, ...]
    missing: tuple[str, ...]
    warnings: tuple[EvaluationWarning, ...]

    def to_breakdown(self) -> dict[str, Any]:
        return {
            "scoring_version": DEAL_SCORING_VERSION,
            "score": None if self.score is None else str(self.score),
            "missing_components": list(self.missing),
            "components": [component.to_contract() for component in self.components],
        }


@dataclass(frozen=True, slots=True)
class MonetizationScoreResult:
    """Deterministic Monetization Score with its breakdown."""

    candidate_id: str
    score: int | None
    fully_calibrated: bool
    weight_covered: int
    components: tuple[ScoreComponent, ...]
    warnings: tuple[EvaluationWarning, ...]

    def to_breakdown(self) -> dict[str, Any]:
        return {
            "scoring_version": MONETIZATION_SCORING_VERSION,
            "score": self.score,
            "fully_calibrated": self.fully_calibrated,
            "weight_covered": self.weight_covered,
            "components": [component.to_contract() for component in self.components],
        }


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    """Deterministic Confidence with its level and breakdown."""

    candidate_id: str
    score: int | None
    level: ConfidenceLevel | None
    fully_calibrated: bool
    weight_covered: int
    components: tuple[ScoreComponent, ...]
    warnings: tuple[EvaluationWarning, ...]

    def to_breakdown(self) -> dict[str, Any]:
        return {
            "scoring_version": CONFIDENCE_SCORING_VERSION,
            "score": self.score,
            "level": None if self.level is None else self.level.value,
            "fully_calibrated": self.fully_calibrated,
            "weight_covered": self.weight_covered,
            "components": [component.to_contract() for component in self.components],
        }


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Immutable, versioned Evaluation of one Candidate (AUT-030)."""

    evaluation_id: str
    candidate_id: str
    brand: Brand
    deal_score: Decimal | None
    monetization_score: int | None
    confidence: ConfidenceLevel | None
    decision: Decision
    auto_eligible: bool
    passed_rules: tuple[str, ...]
    failed_rules: tuple[HardRuleViolation, ...]
    warnings: tuple[EvaluationWarning, ...]
    breakdown: Mapping[str, Any]
    feature_snapshot: Mapping[str, Any]
    scoring_version: str
    deal_scoring_version: str
    monetization_scoring_version: str
    confidence_scoring_version: str
    taxonomy_version: str | None
    taxonomy_hash: str | None
    audit_event_id: str
    created_at: datetime
    correlation_id: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "status": "EVALUATED",
            "evaluation_id": self.evaluation_id,
            "candidate_id": self.candidate_id,
            "brand": self.brand.value,
            "deal_score": None if self.deal_score is None else str(self.deal_score),
            "monetization_score": self.monetization_score,
            "confidence": None if self.confidence is None else self.confidence.value,
            "decision": self.decision.value,
            "auto_eligible": self.auto_eligible,
            "passed_rules": list(self.passed_rules),
            "failed_rules": [rule.to_contract() for rule in self.failed_rules],
            "warnings": [warning.to_contract() for warning in self.warnings],
            "breakdown": dict(self.breakdown),
            "feature_snapshot": dict(self.feature_snapshot),
            "scoring_version": self.scoring_version,
            "deal_scoring_version": self.deal_scoring_version,
            "monetization_scoring_version": self.monetization_scoring_version,
            "confidence_scoring_version": self.confidence_scoring_version,
            "taxonomy_version": self.taxonomy_version,
            "taxonomy_hash": self.taxonomy_hash,
            "audit_event_id": self.audit_event_id,
            "created_at": _to_utc(self.created_at).isoformat(),
            "correlation_id": self.correlation_id,
        }


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _require_score(value: Any, *, component: str) -> int:
    """Validate a component score, failing closed with a structured error."""

    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise evaluation_input_invalid_error(
            "componente de score deve ser inteiro entre 0 e 100",
            context={"component": component, "score": value if isinstance(value, int) else None},
        )
    return value


def _weighted_score(components: Sequence[ScoreComponent]) -> int | None:
    present = [
        component for component in components if component.present and component.score is not None
    ]
    weight_covered = sum(component.weight for component in present)
    if not present or weight_covered == 0:
        return None
    weighted = sum(Decimal(component.score or 0) * component.weight for component in present)
    return int((weighted / Decimal(weight_covered)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def confidence_level_for(score: int | None) -> ConfidenceLevel | None:
    """Map a ``0..100`` Confidence score to its approved band."""

    if score is None:
        return None
    if score < CONFIDENCE_MEDIUM_FROM:
        return ConfidenceLevel.LOW
    if score < CONFIDENCE_HIGH_FROM:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.HIGH


def compute_deal_score(*, candidate_id: str, facts: DealFacts) -> DealScoreResult:
    """Compute the deterministic Deal Score from the four macro components.

    Every macro component is required. A missing or uncalibrated component keeps
    the score ``None`` and produces the blocking ``INSUFFICIENT_REQUIRED_DATA``
    Hard Rule at the Evaluation level, so an incomplete Candidate is never
    approved. Commission is deliberately absent from the inputs (AUT-051).
    """

    components: list[ScoreComponent] = []
    missing: list[str] = []
    warnings: list[EvaluationWarning] = []
    for name, weight, value in (
        ("price_opportunity", WEIGHT_PRICE_OPPORTUNITY, facts.price_opportunity),
        ("seller_quality", WEIGHT_SELLER_QUALITY, facts.seller_quality),
        ("demand", WEIGHT_DEMAND, facts.demand),
        ("brand_fit", WEIGHT_BRAND_FIT, facts.brand_fit),
    ):
        if value is None:
            components.append(
                ScoreComponent(
                    name=name, weight=weight, score=None, present=False, reason=REASON_MISSING
                )
            )
            missing.append(name)
            warnings.append(
                EvaluationWarning(
                    code=WARNING_DEAL_COMPONENT_MISSING,
                    message="Componente obrigatório do Deal Score ausente; dado ausente é bloqueante",
                    context={"component": name},
                )
            )
            continue
        score = _require_score(value, component=name)
        components.append(
            ScoreComponent(name=name, weight=weight, score=score, present=True, reason=REASON_OK)
        )

    if missing:
        deal_score: Decimal | None = None
    else:
        weighted = sum(Decimal(component.score or 0) * component.weight for component in components)
        deal_score = (weighted / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return DealScoreResult(
        candidate_id=candidate_id,
        score=deal_score,
        components=tuple(components),
        missing=tuple(missing),
        warnings=tuple(warnings),
    )


def compute_monetization_score(
    *, candidate_id: str, facts: MonetizationFacts
) -> MonetizationScoreResult:
    """Compute the deterministic Monetization Score.

    Conversion Evidence starts at the approved neutral ``50`` until the Radar has
    its own attribution data (AUT-053); the other components are excluded from
    the partial aggregate when absent instead of becoming an arbitrary zero. The
    result never approves a rejected offer: the decision matrix ignores it and it
    only orders already acceptable opportunities (AUT-052, AUT-060).
    """

    components: list[ScoreComponent] = []
    warnings: list[EvaluationWarning] = []
    for name, weight, value in (
        ("estimated_commission", WEIGHT_ESTIMATED_COMMISSION, facts.estimated_commission),
        (
            "effective_commission_percent",
            WEIGHT_EFFECTIVE_COMMISSION_PERCENT,
            facts.effective_commission_percent,
        ),
        ("conversion_evidence", WEIGHT_CONVERSION_EVIDENCE, facts.conversion_evidence),
        ("extra_commission", WEIGHT_EXTRA_COMMISSION, facts.extra_commission),
    ):
        if value is None:
            if name == "conversion_evidence":
                components.append(
                    ScoreComponent(
                        name=name,
                        weight=weight,
                        score=NEUTRAL_CONVERSION_EVIDENCE,
                        present=True,
                        reason=REASON_NEUTRAL,
                    )
                )
                warnings.append(
                    EvaluationWarning(
                        code=WARNING_CONVERSION_EVIDENCE_NEUTRAL,
                        message=(
                            "Sem histórico próprio de conversão; Conversion Evidence "
                            "usa o neutro aprovado 50"
                        ),
                        context={"component": name, "score": NEUTRAL_CONVERSION_EVIDENCE},
                    )
                )
                continue
            components.append(
                ScoreComponent(
                    name=name, weight=weight, score=None, present=False, reason=REASON_MISSING
                )
            )
            warnings.append(
                EvaluationWarning(
                    code=WARNING_MONETIZATION_COMPONENT_MISSING,
                    message="Componente de Monetization ausente; excluído do agregado parcial",
                    context={"component": name},
                )
            )
            continue
        score = _require_score(value, component=name)
        components.append(
            ScoreComponent(name=name, weight=weight, score=score, present=True, reason=REASON_OK)
        )

    score = _weighted_score(components)
    weight_covered = sum(component.weight for component in components if component.present)
    fully_calibrated = all(
        component.present and component.reason == REASON_OK for component in components
    )
    return MonetizationScoreResult(
        candidate_id=candidate_id,
        score=score,
        fully_calibrated=fully_calibrated,
        weight_covered=weight_covered,
        components=tuple(components),
        warnings=tuple(warnings),
    )


def compute_confidence(*, candidate_id: str, facts: ConfidenceFacts) -> ConfidenceResult:
    """Compute the deterministic Confidence independently of the Deal Score.

    Missing components are explicit gaps excluded from the partial aggregate;
    when no component is available Confidence is ``None`` (never an invented
    level). The approved bands are ``0..49 LOW``, ``50..79 MEDIUM`` and
    ``80..100 HIGH``.
    """

    components: list[ScoreComponent] = []
    warnings: list[EvaluationWarning] = []
    for name, weight, value in (
        ("source_reliability", WEIGHT_SOURCE_RELIABILITY, facts.source_reliability),
        ("freshness", WEIGHT_FRESHNESS, facts.freshness),
        ("completeness", WEIGHT_COMPLETENESS, facts.completeness),
        ("price_history_depth", WEIGHT_PRICE_HISTORY_DEPTH, facts.price_history_depth),
        ("cross_validation", WEIGHT_CROSS_VALIDATION, facts.cross_validation),
    ):
        if value is None:
            components.append(
                ScoreComponent(
                    name=name, weight=weight, score=None, present=False, reason=REASON_MISSING
                )
            )
            warnings.append(
                EvaluationWarning(
                    code=WARNING_CONFIDENCE_COMPONENT_MISSING,
                    message="Componente de Confidence ausente; excluído do agregado parcial",
                    context={"component": name},
                )
            )
            continue
        score = _require_score(value, component=name)
        components.append(
            ScoreComponent(name=name, weight=weight, score=score, present=True, reason=REASON_OK)
        )

    score = _weighted_score(components)
    weight_covered = sum(component.weight for component in components if component.present)
    return ConfidenceResult(
        candidate_id=candidate_id,
        score=score,
        level=confidence_level_for(score),
        fully_calibrated=all(component.present for component in components),
        weight_covered=weight_covered,
        components=tuple(components),
        warnings=tuple(warnings),
    )


def decide(
    *,
    deal_score: Decimal | None,
    confidence: ConfidenceLevel | None,
    failed_rules: Sequence[HardRuleViolation],
) -> Decision:
    """Apply the Deal x Confidence decision matrix (``docs/05_SCORING_ENGINE.md``).

    Hard Rules always win (AUT-056). A missing Deal Score is a blocking gap, so
    it rejects. Monetization is intentionally not an input: it never approves a
    rejected offer and never overrides a guardrail (AUT-051, AUT-052).
    """

    if failed_rules:
        return Decision.REJECT
    if deal_score is None or deal_score < DEAL_REJECT_BELOW:
        return Decision.REJECT
    if deal_score < DEAL_STRONG_FROM:
        if confidence is ConfidenceLevel.LOW or confidence is None:
            return Decision.REJECT
        return Decision.REVIEW
    if confidence is ConfidenceLevel.HIGH or confidence is ConfidenceLevel.MEDIUM:
        return Decision.APPROVE
    return Decision.REVIEW


def _hard_rule_violation(rule: HardRule | str, *, context: Mapping[str, Any]) -> HardRuleViolation:
    value = rule.value if isinstance(rule, HardRule) else str(rule)
    messages = {
        HardRule.INSUFFICIENT_REQUIRED_DATA.value: (
            "Dados obrigatórios ausentes; Hard Rule bloqueia antes de score, IA, link e publicação"
        ),
        HardRule.OUT_OF_SCOPE_CATEGORY.value: (
            "Categoria fora do escopo da marca; Hard Rule precede score e IA"
        ),
    }
    message = messages.get(value, "Hard Rule declarada para este Candidate; precede score e IA")
    return HardRuleViolation(rule=value, message=message, context=dict(context))


def build_evaluation(
    *,
    evaluation_id: str,
    candidate_id: str,
    brand: Brand,
    deal: DealFacts,
    correlation_id: str,
    created_at: datetime,
    audit_event_id: str,
    monetization: MonetizationFacts | None = None,
    confidence: ConfidenceFacts | None = None,
    declared_hard_rules: Sequence[HardRule] = (),
    classification_hard_rules: Sequence[HardRuleViolation] = (),
    classification_warnings: Sequence[EvaluationWarning] = (),
    taxonomy_version: str | None = None,
    taxonomy_hash: str | None = None,
) -> Evaluation:
    """Compose the immutable Evaluation and apply the decision matrix.

    The result carries the feature snapshot, the breakdown and the scoring
    versions so it can be persisted append-only and audited later (AUT-030,
    AUT-065).
    """

    deal_result = compute_deal_score(candidate_id=candidate_id, facts=deal)
    monetization_result = compute_monetization_score(
        candidate_id=candidate_id, facts=monetization or MonetizationFacts()
    )
    confidence_result = compute_confidence(
        candidate_id=candidate_id, facts=confidence or ConfidenceFacts()
    )

    failed: dict[str, HardRuleViolation] = {}
    for violation in classification_hard_rules:
        failed.setdefault(violation.rule, violation)
    if deal_result.missing:
        violation = _hard_rule_violation(
            HardRule.INSUFFICIENT_REQUIRED_DATA,
            context={"missing_components": list(deal_result.missing)},
        )
        failed.setdefault(violation.rule, violation)
    for rule in declared_hard_rules:
        violation = _hard_rule_violation(rule, context={"declared": True})
        failed.setdefault(violation.rule, violation)

    failed_rules = tuple(failed.values())
    passed_rules = tuple(sorted(rule for rule in BASE_HARD_RULE_CHECKS if rule not in failed))

    decision = decide(
        deal_score=deal_result.score,
        confidence=confidence_result.level,
        failed_rules=failed_rules,
    )
    auto_eligible = (
        not failed_rules
        and deal_result.score is not None
        and deal_result.score >= DEAL_STRONG_FROM
        and confidence_result.level is ConfidenceLevel.HIGH
    )

    warnings = (
        tuple(classification_warnings)
        + deal_result.warnings
        + monetization_result.warnings
        + confidence_result.warnings
    )

    breakdown: dict[str, Any] = {
        "deal": deal_result.to_breakdown(),
        "monetization": monetization_result.to_breakdown(),
        "confidence": confidence_result.to_breakdown(),
    }
    feature_snapshot: dict[str, Any] = {
        "brand": brand.value,
        "taxonomy_version": taxonomy_version,
        "taxonomy_hash": taxonomy_hash,
        "deal": {
            "price_opportunity": deal.price_opportunity,
            "seller_quality": deal.seller_quality,
            "demand": deal.demand,
            "brand_fit": deal.brand_fit,
        },
        "monetization": {
            "estimated_commission": (monetization or MonetizationFacts()).estimated_commission,
            "effective_commission_percent": (
                monetization or MonetizationFacts()
            ).effective_commission_percent,
            "conversion_evidence": (monetization or MonetizationFacts()).conversion_evidence,
            "extra_commission": (monetization or MonetizationFacts()).extra_commission,
        },
        "confidence": {
            "source_reliability": (confidence or ConfidenceFacts()).source_reliability,
            "freshness": (confidence or ConfidenceFacts()).freshness,
            "completeness": (confidence or ConfidenceFacts()).completeness,
            "price_history_depth": (confidence or ConfidenceFacts()).price_history_depth,
            "cross_validation": (confidence or ConfidenceFacts()).cross_validation,
        },
        "declared_hard_rules": [rule.value for rule in declared_hard_rules],
    }

    return Evaluation(
        evaluation_id=evaluation_id,
        candidate_id=candidate_id,
        brand=brand,
        deal_score=deal_result.score,
        monetization_score=monetization_result.score,
        confidence=confidence_result.level,
        decision=decision,
        auto_eligible=auto_eligible,
        passed_rules=passed_rules,
        failed_rules=failed_rules,
        warnings=warnings,
        breakdown=breakdown,
        feature_snapshot=feature_snapshot,
        scoring_version=EVALUATION_SCORING_VERSION,
        deal_scoring_version=DEAL_SCORING_VERSION,
        monetization_scoring_version=MONETIZATION_SCORING_VERSION,
        confidence_scoring_version=CONFIDENCE_SCORING_VERSION,
        taxonomy_version=taxonomy_version,
        taxonomy_hash=taxonomy_hash,
        audit_event_id=audit_event_id,
        created_at=_to_utc(created_at),
        correlation_id=correlation_id,
    )


__all__ = [
    "BASE_HARD_RULE_CHECKS",
    "CONFIDENCE_HIGH_FROM",
    "CONFIDENCE_MEDIUM_FROM",
    "CONFIDENCE_SCORING_VERSION",
    "DEAL_REJECT_BELOW",
    "DEAL_SCORING_VERSION",
    "DEAL_STRONG_FROM",
    "EVALUATION_INPUT_INVALID",
    "EVALUATION_SCHEMA_VERSION",
    "EVALUATION_SCORING_VERSION",
    "MONETIZATION_SCORING_VERSION",
    "NEUTRAL_CONVERSION_EVIDENCE",
    "REASON_MISSING",
    "REASON_NEUTRAL",
    "REASON_OK",
    "WARNING_CONFIDENCE_COMPONENT_MISSING",
    "WARNING_CONVERSION_EVIDENCE_NEUTRAL",
    "WARNING_DEAL_COMPONENT_MISSING",
    "WARNING_MONETIZATION_COMPONENT_MISSING",
    "WEIGHT_BRAND_FIT",
    "WEIGHT_COMPLETENESS",
    "WEIGHT_CONVERSION_EVIDENCE",
    "WEIGHT_CROSS_VALIDATION",
    "WEIGHT_DEMAND",
    "WEIGHT_EFFECTIVE_COMMISSION_PERCENT",
    "WEIGHT_ESTIMATED_COMMISSION",
    "WEIGHT_EXTRA_COMMISSION",
    "WEIGHT_FRESHNESS",
    "WEIGHT_PRICE_HISTORY_DEPTH",
    "WEIGHT_PRICE_OPPORTUNITY",
    "WEIGHT_SELLER_QUALITY",
    "WEIGHT_SOURCE_RELIABILITY",
    "ConfidenceFacts",
    "ConfidenceLevel",
    "ConfidenceResult",
    "DealFacts",
    "DealScoreResult",
    "Decision",
    "Evaluation",
    "EvaluationError",
    "EvaluationWarning",
    "HardRule",
    "MonetizationFacts",
    "MonetizationScoreResult",
    "ScoreComponent",
    "build_evaluation",
    "compute_confidence",
    "compute_deal_score",
    "compute_monetization_score",
    "confidence_level_for",
    "decide",
    "evaluation_input_invalid_error",
]
