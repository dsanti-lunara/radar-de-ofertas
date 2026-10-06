"""Deterministic Purchase Source comparison and guardrail (RDR-031).

This module implements the *Purchase Source Guardrail* of
``docs/05_SCORING_ENGINE.md``: when the chosen (affiliate) purchase source costs
materially more than another reliable option of the same Product, the selection
must go to ``REVIEW`` or be replaced according to the configured policy.

Three rules are load-bearing:

* commission is never an input. The comparison has no commission field and the
  result is identical no matter how much commission the affiliate source pays,
  so monetization can never favour a materially worse option (AUT-051, AUT-062);
* only *reliable and comparable* sources take part in the comparison. Product
  equivalence must be established (``product_equivalence_id``) and the commercial
  conditions must match; otherwise the source is an explicit gap, not a valid
  comparison (``PURCHASE_SOURCE_NOT_EQUIVALENT`` /
  ``PURCHASE_SOURCE_CONDITIONS_NOT_COMPARABLE``);
* the effective price is ``price + shipping - confirmed coupon`` and is only
  computed when shipping is known. A coupon that is not ``CONFIRMED`` never
  reduces the effective price (AUT-048, AUT-049). A source without a reliable
  effective price is excluded from the comparison instead of being compared on an
  invented number.

The module is framework-free (no FastAPI/SQLAlchemy/Chrome) so the domain stays
independent from infrastructure (AUT-397), and it never calls AI to decide
anything (AUT-031). Absence of a reliable comparison is reported explicitly and
never invents a reference.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from radar.domain.capture import Evidence
from radar.domain.errors import RadarError, RadarException
from radar.domain.price_opportunity import Coupon

#: Version of the public purchase source contract.
PURCHASE_SOURCE_SCHEMA_VERSION = "1.0"

#: Version of the purchase source policy document schema.
PURCHASE_SOURCE_POLICY_SCHEMA_VERSION = "1.0"

#: Scoring version stored alongside the decision (``docs/05_SCORING_ENGINE.md``).
PURCHASE_SOURCE_SCORING_VERSION = "purchase-source-1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
PURCHASE_SOURCE_INPUT_INVALID = "RAD-CAP-012"
PURCHASE_SOURCE_POLICY_INVALID = "RAD-CFG-008"

#: Entity type recorded on the Evidence rows of a decision.
ENTITY_PURCHASE_SOURCE_DECISION = "purchase_source_decision"

#: Provenance source recorded on the Evidence rows of a decision.
EVIDENCE_SOURCE_PURCHASE_SOURCE_COMPARISON = "purchase_source_comparison"

#: Warning codes emitted by the comparison.
WARNING_PRODUCT_NOT_IDENTIFIED = "PURCHASE_SOURCE_PRODUCT_NOT_IDENTIFIED"
WARNING_NOT_EQUIVALENT = "PURCHASE_SOURCE_NOT_EQUIVALENT"
WARNING_CONDITIONS_NOT_COMPARABLE = "PURCHASE_SOURCE_CONDITIONS_NOT_COMPARABLE"
WARNING_UNRELIABLE_PRICE = "PURCHASE_SOURCE_UNRELIABLE_PRICE"
WARNING_NO_RELIABLE_COMPARISON = "PURCHASE_SOURCE_NO_RELIABLE_COMPARISON"
WARNING_MATERIAL_DIFFERENCE = "PURCHASE_SOURCE_MATERIAL_DIFFERENCE"
WARNING_COMMISSION_IGNORED = "PURCHASE_SOURCE_COMMISSION_IGNORED"

#: Human-readable reason attached to each evaluated source.
REASON_CHOSEN = "chosen"
REASON_OK = "ok"
REASON_NOT_EQUIVALENT = "not_equivalent"
REASON_NOT_COMPARABLE = "conditions_not_comparable"
REASON_UNRELIABLE = "unreliable_effective_price"
REASON_PRODUCT_NOT_IDENTIFIED = "product_not_identified"

#: Evidence fields recorded for a decision.
EVIDENCE_FIELD_CHOSEN_EFFECTIVE_PRICE = "chosen_effective_price"
EVIDENCE_FIELD_ALTERNATIVE_EFFECTIVE_PRICE = "alternative_effective_price"
EVIDENCE_FIELD_DIFFERENCE_PERCENT = "difference_percent"
EVIDENCE_FIELD_THRESHOLD_PERCENT = "reference_difference_percent"
EVIDENCE_FIELD_DECISION = "decision"


class PurchaseSourceDecision(StrEnum):
    """Outcome of the purchase source guardrail."""

    KEEP = "KEEP"
    REVIEW = "REVIEW"
    SUBSTITUTE = "SUBSTITUTE"


class MaterialDifferenceAction(StrEnum):
    """Configured action when the affiliate source is materially worse."""

    REVIEW = "REVIEW"
    SUBSTITUTE = "SUBSTITUTE"


class PurchaseSourceError(RadarException):
    """Raised when a Purchase Source request cannot be satisfied."""


class PurchaseSourcePolicyInvalidError(RadarException):
    """Raised when the Purchase Source policy configuration is invalid."""


def purchase_source_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> PurchaseSourceError:
    """Build the structured error for invalid Purchase Source inputs."""

    return PurchaseSourceError(
        RadarError(
            code=PURCHASE_SOURCE_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir as ofertas comparadas e consultar novamente",
            context=dict(context or {}),
        )
    )


def purchase_source_policy_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> PurchaseSourcePolicyInvalidError:
    """Build the structured error for an invalid Purchase Source policy."""

    return PurchaseSourcePolicyInvalidError(
        RadarError(
            code=PURCHASE_SOURCE_POLICY_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de policy e validar novamente",
            context=dict(context or {}),
        )
    )


@dataclass(frozen=True, slots=True)
class PurchaseSourcePolicy:
    """Versioned, hashed policy of the purchase source guardrail.

    ``reference_difference_percent`` is the material-difference threshold (the
    SDD freezes an initial reference of ``>8%``, configurable) and
    ``on_material_difference`` states whether a material difference goes to
    ``REVIEW`` or is substituted.
    """

    policy_version: str
    content_hash: str
    reference_difference_percent: Decimal
    on_material_difference: MaterialDifferenceAction

    def to_contract(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_hash": self.content_hash,
            "reference_difference_percent": str(self.reference_difference_percent),
            "on_material_difference": self.on_material_difference.value,
        }


@dataclass(frozen=True, slots=True)
class PurchaseSource:
    """One commercial purchase source considered by the guardrail.

    ``product_equivalence_id`` establishes that this source sells the *same*
    Product; ``conditions`` carries the comparable commercial conditions (for
    example condition/variant). Neither field is inferred here.
    """

    source_id: str
    price: Decimal
    marketplace: str | None = None
    url: str | None = None
    shipping_cost: Decimal | None = None
    coupon: Coupon = field(default_factory=Coupon)
    product_equivalence_id: str | None = None
    conditions: Mapping[str, str] = field(default_factory=dict)
    affiliate_commission: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PurchaseSourceEvaluation:
    """Explainable evaluation of one source, used as evidence."""

    source_id: str
    role: str
    marketplace: str | None
    url: str | None
    price: Decimal
    shipping_cost: Decimal | None
    coupon_state: str
    coupon_amount: Decimal | None
    effective_price: Decimal | None
    equivalent: bool
    conditions_comparable: bool
    eligible: bool
    reason: str
    affiliate_commission: Decimal | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "role": self.role,
            "marketplace": self.marketplace,
            "url": self.url,
            "price": str(self.price),
            "shipping_cost": None if self.shipping_cost is None else str(self.shipping_cost),
            "coupon_state": self.coupon_state,
            "coupon_amount": None if self.coupon_amount is None else str(self.coupon_amount),
            "effective_price": None if self.effective_price is None else str(self.effective_price),
            "product_equivalent": self.equivalent,
            "conditions_comparable": self.conditions_comparable,
            "eligible": self.eligible,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PurchaseSourceWarning:
    """Explicit, non-fatal gap emitted by the comparison."""

    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class PurchaseSourceResult:
    """Deterministic purchase source decision with its evidence."""

    candidate_id: str
    decision: PurchaseSourceDecision
    chosen_source_id: str
    best_alternative_source_id: str | None
    chosen_effective_price: Decimal | None
    alternative_effective_price: Decimal | None
    difference_percent: Decimal | None
    material: bool
    threshold_percent: Decimal
    substituted_source_id: str | None
    policy: PurchaseSourcePolicy
    sources: tuple[PurchaseSourceEvaluation, ...]
    warnings: tuple[PurchaseSourceWarning, ...]
    as_of: datetime
    commission_considered: bool = False

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": PURCHASE_SOURCE_SCHEMA_VERSION,
            "status": "DECIDED",
            "scoring_version": PURCHASE_SOURCE_SCORING_VERSION,
            "candidate_id": self.candidate_id,
            "decision": self.decision.value,
            "chosen_source_id": self.chosen_source_id,
            "best_alternative_source_id": self.best_alternative_source_id,
            "substituted_source_id": self.substituted_source_id,
            "chosen_effective_price": (
                None if self.chosen_effective_price is None else str(self.chosen_effective_price)
            ),
            "alternative_effective_price": (
                None
                if self.alternative_effective_price is None
                else str(self.alternative_effective_price)
            ),
            "difference_percent": (
                None if self.difference_percent is None else str(self.difference_percent)
            ),
            "material": self.material,
            "reference_difference_percent": str(self.threshold_percent),
            "commission_considered": self.commission_considered,
            "policy": self.policy.to_contract(),
            "sources": [source.to_contract() for source in self.sources],
            "warnings": [warning.to_contract() for warning in self.warnings],
            "as_of": _to_utc(self.as_of).isoformat(),
        }


@dataclass(frozen=True, slots=True)
class PurchaseSourceDecisionRecord:
    """Persisted, auditable purchase source decision (immutable/append-only)."""

    decision_id: str
    result: PurchaseSourceResult
    correlation_id: str
    audit_event_id: str
    created_at: datetime
    evidence: tuple[Evidence, ...] = ()

    def to_contract(self) -> dict[str, Any]:
        return {
            **self.result.to_contract(),
            "decision_id": self.decision_id,
            "correlation_id": self.correlation_id,
            "audit_event_id": self.audit_event_id,
            "created_at": _to_utc(self.created_at).isoformat(),
            "evidence": [
                {
                    "evidence_id": item.id,
                    "field": item.field_name,
                    "value": item.value,
                    "source_type": item.source_type,
                }
                for item in self.evidence
            ],
        }


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _round_percent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _conditions_document(conditions: Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in sorted(conditions.items())}


def _effective_price(source: PurchaseSource) -> Decimal | None:
    """Return the reliable effective price or ``None`` when shipping is unknown."""

    if source.shipping_cost is None:
        return None
    applied = source.coupon.applied_amount()
    return source.price + source.shipping_cost - (applied or Decimal(0))


def _validate_source(source: PurchaseSource) -> None:
    if not source.source_id.strip():
        raise purchase_source_input_invalid_error(
            "source_id é obrigatório", context={"field": "source_id"}
        )
    if not source.price.is_finite() or source.price <= 0:
        raise purchase_source_input_invalid_error(
            "price deve ser maior que zero",
            context={"source_id": source.source_id, "field": "price"},
        )
    if source.shipping_cost is not None and (
        not source.shipping_cost.is_finite() or source.shipping_cost < 0
    ):
        raise purchase_source_input_invalid_error(
            "shipping_cost não pode ser negativo",
            context={"source_id": source.source_id, "field": "shipping_cost"},
        )
    if source.affiliate_commission is not None and (
        not source.affiliate_commission.is_finite() or source.affiliate_commission < 0
    ):
        raise purchase_source_input_invalid_error(
            "affiliate_commission não pode ser negativa",
            context={"source_id": source.source_id, "field": "affiliate_commission"},
        )


def _evaluate_source(
    source: PurchaseSource, *, role: str, chosen: PurchaseSource
) -> PurchaseSourceEvaluation:
    effective = _effective_price(source)
    equivalent = (
        source.product_equivalence_id is not None
        and source.product_equivalence_id == chosen.product_equivalence_id
    )
    if role == REASON_CHOSEN:
        # The chosen source is trivially comparable to itself; equivalence still
        # requires that the Product was positively identified.
        conditions_comparable = True
    else:
        conditions_comparable = _conditions_document(source.conditions) == _conditions_document(
            chosen.conditions
        )
    reliable = effective is not None
    eligible = equivalent and conditions_comparable and reliable
    if role == REASON_CHOSEN:
        reason = REASON_CHOSEN
    elif chosen.product_equivalence_id is None:
        reason = REASON_PRODUCT_NOT_IDENTIFIED
    elif not equivalent:
        reason = REASON_NOT_EQUIVALENT
    elif not conditions_comparable:
        reason = REASON_NOT_COMPARABLE
    elif not reliable:
        reason = REASON_UNRELIABLE
    else:
        reason = REASON_OK
    return PurchaseSourceEvaluation(
        source_id=source.source_id,
        role=role,
        marketplace=source.marketplace,
        url=source.url,
        price=source.price,
        shipping_cost=source.shipping_cost,
        coupon_state=source.coupon.state.value,
        coupon_amount=source.coupon.amount,
        effective_price=effective,
        equivalent=equivalent,
        conditions_comparable=conditions_comparable,
        eligible=eligible,
        reason=reason,
        affiliate_commission=source.affiliate_commission,
    )


def _alternative_warning(evaluation: PurchaseSourceEvaluation) -> PurchaseSourceWarning | None:
    context = {"source_id": evaluation.source_id}
    if evaluation.reason == REASON_PRODUCT_NOT_IDENTIFIED:
        return None
    if evaluation.reason == REASON_NOT_EQUIVALENT:
        return PurchaseSourceWarning(
            code=WARNING_NOT_EQUIVALENT,
            message=(
                "Produto não identificado como equivalente; a oferta não é uma comparação válida"
            ),
            context=context,
        )
    if evaluation.reason == REASON_NOT_COMPARABLE:
        return PurchaseSourceWarning(
            code=WARNING_CONDITIONS_NOT_COMPARABLE,
            message="Condições comerciais não comparáveis; a oferta não é uma comparação válida",
            context=context,
        )
    if evaluation.reason == REASON_UNRELIABLE:
        return PurchaseSourceWarning(
            code=WARNING_UNRELIABLE_PRICE,
            message=(
                "Frete/cupom não confiáveis; preço efetivo indisponível e oferta "
                "excluída da comparação"
            ),
            context=context,
        )
    return None


def compute_purchase_source(
    *,
    candidate_id: str,
    chosen: PurchaseSource,
    alternatives: Sequence[PurchaseSource],
    policy: PurchaseSourcePolicy,
    as_of: datetime,
) -> PurchaseSourceResult:
    """Compute the deterministic purchase source decision.

    The chosen source is the Candidate's own (affiliate) offer. The function
    never mutates its inputs and is reproducible for the same sources and policy.
    """

    _validate_source(chosen)
    for alternative in alternatives:
        _validate_source(alternative)

    seen = {chosen.source_id}
    for alternative in alternatives:
        if alternative.source_id in seen:
            raise purchase_source_input_invalid_error(
                "source_id duplicado entre ofertas comparadas",
                context={"source_id": alternative.source_id},
            )
        seen.add(alternative.source_id)

    reference_time = _to_utc(as_of)
    warnings: list[PurchaseSourceWarning] = []

    chosen_evaluation = _evaluate_source(chosen, role=REASON_CHOSEN, chosen=chosen)
    evaluations = [chosen_evaluation]
    for alternative in sorted(alternatives, key=lambda item: item.source_id):
        evaluation = _evaluate_source(alternative, role="alternative", chosen=chosen)
        evaluations.append(evaluation)
        warning = _alternative_warning(evaluation)
        if warning is not None:
            warnings.append(warning)

    if chosen.product_equivalence_id is None:
        warnings.append(
            PurchaseSourceWarning(
                code=WARNING_PRODUCT_NOT_IDENTIFIED,
                message=(
                    "Produto do Candidate não identificado como equivalente; não há "
                    "comparação válida entre fontes de compra"
                ),
                context={"chosen_source_id": chosen.source_id},
            )
        )

    if chosen.affiliate_commission is not None:
        warnings.append(
            PurchaseSourceWarning(
                code=WARNING_COMMISSION_IGNORED,
                message=(
                    "Comissão afiliada não é considerada pelo guardrail de fonte de "
                    "compra; nunca favorece a seleção afiliada"
                ),
                context={"chosen_source_id": chosen.source_id},
            )
        )

    chosen_effective = chosen_evaluation.effective_price
    eligible = [item for item in evaluations if item.role == "alternative" and item.eligible]

    decision = PurchaseSourceDecision.KEEP
    best: PurchaseSourceEvaluation | None = None
    difference: Decimal | None = None
    material = False
    substituted_source_id: str | None = None

    if chosen_effective is None or not eligible:
        warnings.append(
            PurchaseSourceWarning(
                code=WARNING_NO_RELIABLE_COMPARISON,
                message=(
                    "Sem referência confiável e comparável; o guardrail de fonte de "
                    "compra não inventa comparação"
                ),
                context={"chosen_source_id": chosen.source_id},
            )
        )
    else:
        best = min(
            eligible,
            key=lambda item: (item.effective_price or Decimal(0), item.source_id),
        )
        assert best.effective_price is not None
        difference = _round_percent(
            (chosen_effective - best.effective_price) / best.effective_price * Decimal(100)
        )
        material = difference > policy.reference_difference_percent
        if material:
            decision = (
                PurchaseSourceDecision.SUBSTITUTE
                if policy.on_material_difference is MaterialDifferenceAction.SUBSTITUTE
                else PurchaseSourceDecision.REVIEW
            )
            if decision is PurchaseSourceDecision.SUBSTITUTE:
                substituted_source_id = best.source_id
            warnings.append(
                PurchaseSourceWarning(
                    code=WARNING_MATERIAL_DIFFERENCE,
                    message=(
                        "Fonte afiliada materialmente mais cara que opção confiável "
                        "equivalente; aplicada a policy configurada"
                    ),
                    context={
                        "difference_percent": str(difference),
                        "threshold_percent": str(policy.reference_difference_percent),
                        "decision": decision.value,
                        "best_alternative_source_id": best.source_id,
                    },
                )
            )

    return PurchaseSourceResult(
        candidate_id=candidate_id,
        decision=decision,
        chosen_source_id=chosen.source_id,
        best_alternative_source_id=None if best is None else best.source_id,
        chosen_effective_price=chosen_effective,
        alternative_effective_price=None if best is None else best.effective_price,
        difference_percent=difference,
        material=material,
        threshold_percent=policy.reference_difference_percent,
        substituted_source_id=substituted_source_id,
        policy=policy,
        sources=tuple(evaluations),
        warnings=tuple(warnings),
        as_of=reference_time,
    )


def build_purchase_source_evidence(
    *,
    decision_id: str,
    result: PurchaseSourceResult,
    captured_at: datetime,
    make_id: Callable[[str], str],
) -> tuple[Evidence, ...]:
    """Build the Evidence rows that sustain the decision (AUT-029, AUT-077)."""

    captured = _to_utc(captured_at)
    facts: list[tuple[str, str]] = []
    if result.chosen_effective_price is not None:
        facts.append((EVIDENCE_FIELD_CHOSEN_EFFECTIVE_PRICE, str(result.chosen_effective_price)))
    if result.alternative_effective_price is not None:
        facts.append(
            (EVIDENCE_FIELD_ALTERNATIVE_EFFECTIVE_PRICE, str(result.alternative_effective_price))
        )
    if result.difference_percent is not None:
        facts.append((EVIDENCE_FIELD_DIFFERENCE_PERCENT, str(result.difference_percent)))
    facts.append((EVIDENCE_FIELD_THRESHOLD_PERCENT, str(result.threshold_percent)))
    facts.append((EVIDENCE_FIELD_DECISION, result.decision.value))
    return tuple(
        Evidence(
            id=make_id("evd"),
            entity_type=ENTITY_PURCHASE_SOURCE_DECISION,
            entity_id=decision_id,
            field_name=field_name,
            value=value,
            source_type=EVIDENCE_SOURCE_PURCHASE_SOURCE_COMPARISON,
            captured_at=captured,
        )
        for field_name, value in facts
    )


def _content_hash(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_decimal(value: Any, *, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise purchase_source_policy_invalid_error(
            "limite deve ser decimal, não booleano", context={"field": field_name}
        )
    if isinstance(value, float):
        raise purchase_source_policy_invalid_error(
            "limite deve ser decimal/inteiro, não float binário", context={"field": field_name}
        )
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, str):
        try:
            amount = Decimal(value.strip())
        except InvalidOperation as exc:
            raise purchase_source_policy_invalid_error(
                "limite inválido", context={"field": field_name}
            ) from exc
    else:
        raise purchase_source_policy_invalid_error("limite inválido", context={"field": field_name})
    if not amount.is_finite() or amount < 0:
        raise purchase_source_policy_invalid_error(
            "limite deve ser finito e >= 0", context={"field": field_name}
        )
    return amount


def build_purchase_source_policy(document: Mapping[str, Any]) -> PurchaseSourcePolicy:
    """Build and validate the guardrail policy from a plain document.

    Raises :class:`PurchaseSourcePolicyInvalidError` (``RAD-CFG-008``) on an
    unsupported schema, a missing version, a negative/non-finite threshold or an
    unknown action. A missing action defaults to ``REVIEW`` because substitution
    is a heavier, operator-approved behaviour.
    """

    if not isinstance(document, Mapping):
        raise purchase_source_policy_invalid_error("Policy deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != PURCHASE_SOURCE_POLICY_SCHEMA_VERSION:
        raise purchase_source_policy_invalid_error(
            "schema_version de policy não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("policy_version") or "").strip()
    if not version:
        raise purchase_source_policy_invalid_error("policy_version é obrigatório")

    threshold = _to_decimal(
        document.get("reference_difference_percent", 8),
        field_name="reference_difference_percent",
    )

    raw_action = document.get("on_material_difference", MaterialDifferenceAction.REVIEW.value)
    try:
        action = MaterialDifferenceAction(str(raw_action))
    except ValueError as exc:
        raise purchase_source_policy_invalid_error(
            "on_material_difference inválido",
            context={"allowed": [item.value for item in MaterialDifferenceAction]},
        ) from exc

    normalized = {
        "schema_version": PURCHASE_SOURCE_POLICY_SCHEMA_VERSION,
        "policy_version": version,
        "reference_difference_percent": str(threshold),
        "on_material_difference": action.value,
    }
    return PurchaseSourcePolicy(
        policy_version=version,
        content_hash=_content_hash(normalized),
        reference_difference_percent=threshold,
        on_material_difference=action,
    )


#: Approved baseline policy (RDR-031).
#:
#: ``docs/05_SCORING_ENGINE.md`` freezes an initial reference threshold of ``>8%``
#: and allows ``REVIEW`` or substitution "according to the configured policy".
#: The baseline therefore uses the frozen ``8%`` and ``REVIEW``: substitution is a
#: heavier behaviour and stays an explicit operator configuration instead of being
#: promoted automatically (AUT-257).
APPROVED_PURCHASE_SOURCE_POLICY_DOCUMENT: dict[str, Any] = {
    "schema_version": PURCHASE_SOURCE_POLICY_SCHEMA_VERSION,
    "policy_version": "purchase-source-policy-1.0",
    "reference_difference_percent": "8",
    "on_material_difference": MaterialDifferenceAction.REVIEW.value,
}

#: The approved baseline used when no operator file is configured.
APPROVED_PURCHASE_SOURCE_POLICY: PurchaseSourcePolicy = build_purchase_source_policy(
    APPROVED_PURCHASE_SOURCE_POLICY_DOCUMENT
)


__all__ = [
    "APPROVED_PURCHASE_SOURCE_POLICY",
    "APPROVED_PURCHASE_SOURCE_POLICY_DOCUMENT",
    "ENTITY_PURCHASE_SOURCE_DECISION",
    "EVIDENCE_FIELD_ALTERNATIVE_EFFECTIVE_PRICE",
    "EVIDENCE_FIELD_CHOSEN_EFFECTIVE_PRICE",
    "EVIDENCE_FIELD_DECISION",
    "EVIDENCE_FIELD_DIFFERENCE_PERCENT",
    "EVIDENCE_FIELD_THRESHOLD_PERCENT",
    "EVIDENCE_SOURCE_PURCHASE_SOURCE_COMPARISON",
    "PURCHASE_SOURCE_INPUT_INVALID",
    "PURCHASE_SOURCE_POLICY_INVALID",
    "PURCHASE_SOURCE_POLICY_SCHEMA_VERSION",
    "PURCHASE_SOURCE_SCHEMA_VERSION",
    "PURCHASE_SOURCE_SCORING_VERSION",
    "REASON_CHOSEN",
    "REASON_NOT_COMPARABLE",
    "REASON_NOT_EQUIVALENT",
    "REASON_OK",
    "REASON_PRODUCT_NOT_IDENTIFIED",
    "REASON_UNRELIABLE",
    "WARNING_COMMISSION_IGNORED",
    "WARNING_CONDITIONS_NOT_COMPARABLE",
    "WARNING_MATERIAL_DIFFERENCE",
    "WARNING_NOT_EQUIVALENT",
    "WARNING_NO_RELIABLE_COMPARISON",
    "WARNING_PRODUCT_NOT_IDENTIFIED",
    "WARNING_UNRELIABLE_PRICE",
    "MaterialDifferenceAction",
    "PurchaseSource",
    "PurchaseSourceDecision",
    "PurchaseSourceDecisionRecord",
    "PurchaseSourceError",
    "PurchaseSourceEvaluation",
    "PurchaseSourcePolicy",
    "PurchaseSourcePolicyInvalidError",
    "PurchaseSourceResult",
    "PurchaseSourceWarning",
    "build_purchase_source_evidence",
    "build_purchase_source_policy",
    "compute_purchase_source",
    "purchase_source_input_invalid_error",
    "purchase_source_policy_invalid_error",
]
