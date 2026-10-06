"""Deterministic dedupe and repost rules (RDR-033).

This module implements the *Repost* rules of ``docs/05_SCORING_ENGINE.md`` and
the Hard Rule ``DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE``: before a Candidate can be
sent to the publishing flow again, the guardrail decides whether the offer may
return to the pipeline given a **material change** since the last publication and
the publication history.

The rule is deliberately conservative and configurable (AUT-045, AUT-064):

* the initial reference cooldown is ``72h`` and a price drop since the published
  price of ``>= 10%`` releases the repost; both values come from the approved
  policy, never from a hardcoded constant;
* an irrelevant change never releases a repost while the cooldown is active, so a
  duplicated offer is blocked with ``DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE``;
* a new material coupon or a new material condition only counts when it carries
  ``Evidence`` (AUT-029); a claimed change without evidence is an explicit warning
  and does not become a material change;
* an expired cooldown alone is not enough: the Deal must still be strong
  (``>= 80`` by default) or the repost is blocked with ``DEAL_NOT_STRONG``.

The module is framework-free (no FastAPI/SQLAlchemy/Chrome) so the domain stays
independent from infrastructure (AUT-397), and no AI is called to decide anything
(AUT-031). Publication history is an input, so the guardrail can be demonstrated
with a *fake* publication history before the real publisher exists; the real
publication store belongs to the publishing tickets.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from radar.domain.capture import Evidence
from radar.domain.errors import RadarError, RadarException
from radar.domain.price_opportunity import Coupon

#: Version of the public repost decision contract.
REPOST_SCHEMA_VERSION = "1.0"

#: Version of the repost policy document schema.
REPOST_POLICY_SCHEMA_VERSION = "1.0"

#: Version of the deterministic engine stored alongside the decision (AUT-065).
REPOST_ENGINE_VERSION = "repost-1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
REPOST_INPUT_INVALID = "RAD-CAP-015"
REPOST_POLICY_INVALID = "RAD-CFG-009"

#: Entity type recorded on the Evidence rows of a decision.
ENTITY_REPOST_DECISION = "repost_decision"

#: Provenance source recorded on the Evidence rows of a decision.
EVIDENCE_SOURCE_REPOST_REVIEW = "repost_review"

#: Provenance source recorded on the caller-supplied material evidence.
EVIDENCE_SOURCE_REPOST_INPUT = "repost_input"

#: Warning codes emitted by the guardrail.
WARNING_NO_COMPARABLE_HISTORY = "REPOST_NO_COMPARABLE_HISTORY"
WARNING_COUPON_NOT_CONFIRMED = "REPOST_COUPON_NOT_CONFIRMED"
WARNING_COUPON_WITHOUT_EVIDENCE = "REPOST_COUPON_WITHOUT_EVIDENCE"
WARNING_CONDITION_WITHOUT_EVIDENCE = "REPOST_CONDITION_WITHOUT_EVIDENCE"
WARNING_COOLDOWN_ACTIVE = "REPOST_COOLDOWN_ACTIVE"
WARNING_DEAL_NOT_STRONG = "REPOST_DEAL_NOT_STRONG"
WARNING_DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE = "DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE"
WARNING_MATERIAL_PRICE_DROP = "REPOST_MATERIAL_PRICE_DROP"
WARNING_MATERIAL_COUPON = "REPOST_MATERIAL_COUPON"
WARNING_MATERIAL_CONDITION = "REPOST_MATERIAL_CONDITION"

#: Evidence fields recorded for a decision.
EVIDENCE_FIELD_DECISION = "decision"
EVIDENCE_FIELD_REASON = "reason"
EVIDENCE_FIELD_PUBLISHED_PRICE = "published_price"
EVIDENCE_FIELD_CURRENT_PRICE = "current_price"
EVIDENCE_FIELD_OBSERVED_PRICE_DROP_PERCENT = "observed_price_drop_percent"
EVIDENCE_FIELD_COOLDOWN_EXPIRES_AT = "cooldown_expires_at"
EVIDENCE_FIELD_DEAL_SCORE = "deal_score"
EVIDENCE_FIELD_POLICY = "policy_version"
EVIDENCE_FIELD_MATERIAL_CHANGE = "material_change"
EVIDENCE_FIELD_COUPON_EVIDENCE = "coupon_evidence"
EVIDENCE_FIELD_CONDITION_EVIDENCE = "condition_evidence"


class RepostOutcome(StrEnum):
    """Whether the Candidate may return to the publishing flow."""

    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


class RepostReason(StrEnum):
    """Reason that released or blocked a repost."""

    FIRST_PUBLICATION = "FIRST_PUBLICATION"
    MATERIAL_PRICE_DROP = "MATERIAL_PRICE_DROP"
    MATERIAL_COUPON = "MATERIAL_COUPON"
    MATERIAL_CONDITION = "MATERIAL_CONDITION"
    COOLDOWN_EXPIRED_STRONG_DEAL = "COOLDOWN_EXPIRED_STRONG_DEAL"
    DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE = "DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE"
    DEAL_NOT_STRONG = "DEAL_NOT_STRONG"


class MaterialChangeType(StrEnum):
    """Kind of material change that may release a repost."""

    PRICE_DROP = "PRICE_DROP"
    COUPON = "COUPON"
    CONDITION = "CONDITION"


class RepostEvidenceType(StrEnum):
    """Kind of caller-supplied evidence that sustains a material change."""

    COUPON = "COUPON"
    CONDITION = "CONDITION"


class RepostError(RadarException):
    """Raised when a repost decision cannot be produced."""


class RepostPolicyInvalidError(RadarException):
    """Raised when the repost policy configuration is invalid."""


def repost_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> RepostError:
    """Build the structured error for invalid repost inputs."""

    return RepostError(
        RadarError(
            code=REPOST_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir as publicações/condições informadas e consultar novamente",
            context=dict(context or {}),
        )
    )


def repost_policy_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> RepostPolicyInvalidError:
    """Build the structured error for an invalid repost policy."""

    return RepostPolicyInvalidError(
        RadarError(
            code=REPOST_POLICY_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de policy de repost e validar novamente",
            context=dict(context or {}),
        )
    )


@dataclass(frozen=True, slots=True)
class RepostPolicy:
    """Versioned, hashed policy of the repost guardrail.

    ``cooldown_hours`` and ``price_drop_percent`` are the approved initial
    reference of ``docs/05_SCORING_ENGINE.md`` (72h and 10%). ``strong_deal_threshold``
    is the Deal floor required after the cooldown expires (``>= 80`` by default,
    matching ``DEAL_STRONG_FROM``).
    """

    policy_version: str
    content_hash: str
    cooldown_hours: int
    price_drop_percent: Decimal
    strong_deal_threshold: Decimal

    def to_contract(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_hash": self.content_hash,
            "cooldown_hours": self.cooldown_hours,
            "price_drop_percent": str(self.price_drop_percent),
            "strong_deal_threshold": str(self.strong_deal_threshold),
        }


@dataclass(frozen=True, slots=True)
class PublicationSnapshot:
    """One prior publication of the Candidate, supplied as history.

    Until the real publisher exists, this is a *fake* publication history: the
    snapshot carries only the facts needed by the guardrail (published price,
    coupon, comparable conditions and when it was published).
    """

    published_at: datetime
    price: Decimal
    publication_id: str | None = None
    coupon: Coupon | None = None
    conditions: Mapping[str, str] = field(default_factory=dict)
    correlation_id: str | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "publication_id": self.publication_id,
            "published_at": _to_utc(self.published_at).isoformat(),
            "price": str(self.price),
            "coupon_state": None if self.coupon is None else self.coupon.state.value,
            "coupon_amount": (
                None
                if self.coupon is None or self.coupon.amount is None
                else str(self.coupon.amount)
            ),
            "coupon_code": None if self.coupon is None else self.coupon.code,
            "conditions": _conditions_document(self.conditions),
        }


@dataclass(frozen=True, slots=True)
class RepostEvidence:
    """Caller-supplied evidence that sustains a material change (AUT-029)."""

    evidence_type: RepostEvidenceType
    reference_id: str
    field: str
    value: str
    source: str = EVIDENCE_SOURCE_REPOST_INPUT

    def to_contract(self) -> dict[str, Any]:
        return {
            "evidence_type": self.evidence_type.value,
            "reference_id": self.reference_id,
            "field": self.field,
            "value": self.value,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class RepostFacts:
    """Current condition of the Candidate evaluated by the guardrail."""

    current_price: Decimal
    deal_score: Decimal | None = None
    coupon: Coupon | None = None
    conditions: Mapping[str, str] = field(default_factory=dict)
    evidence: tuple[RepostEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class MaterialChange:
    """A material change that justifies the repost."""

    change_type: MaterialChangeType
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        return {
            "change_type": self.change_type.value,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True, slots=True)
class RepostWarning:
    """Explicit, non-fatal gap emitted by the guardrail."""

    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class RepostResult:
    """Deterministic dedupe/repost decision with its evidence."""

    candidate_id: str
    decision: RepostOutcome
    reason: RepostReason
    allowed: bool
    material_changes: tuple[MaterialChange, ...]
    publication: PublicationSnapshot | None
    current_price: Decimal
    observed_price_drop_percent: Decimal | None
    cooldown_expires_at: datetime | None
    cooldown_expired: bool
    deal_score: Decimal | None
    policy: RepostPolicy
    warnings: tuple[RepostWarning, ...]
    as_of: datetime

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": REPOST_SCHEMA_VERSION,
            "status": "DECIDED",
            "engine_version": REPOST_ENGINE_VERSION,
            "candidate_id": self.candidate_id,
            "decision": self.decision.value,
            "reason": self.reason.value,
            "allowed": self.allowed,
            "current_price": str(self.current_price),
            "material_changes": [change.to_contract() for change in self.material_changes],
            "publication": None if self.publication is None else self.publication.to_contract(),
            "observed_price_drop_percent": (
                None
                if self.observed_price_drop_percent is None
                else str(self.observed_price_drop_percent)
            ),
            "cooldown_hours": self.policy.cooldown_hours,
            "cooldown_expires_at": (
                None
                if self.cooldown_expires_at is None
                else _to_utc(self.cooldown_expires_at).isoformat()
            ),
            "cooldown_expired": self.cooldown_expired,
            "deal_score": None if self.deal_score is None else str(self.deal_score),
            "strong_deal_threshold": str(self.policy.strong_deal_threshold),
            "price_drop_threshold_percent": str(self.policy.price_drop_percent),
            "policy": self.policy.to_contract(),
            "warnings": [warning.to_contract() for warning in self.warnings],
            "as_of": _to_utc(self.as_of).isoformat(),
        }


@dataclass(frozen=True, slots=True)
class RepostDecisionRecord:
    """Persisted, auditable repost decision (immutable/append-only)."""

    decision_id: str
    result: RepostResult
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
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _conditions_document(conditions: Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in sorted(conditions.items())}


def _coupon_signature(coupon: Coupon | None) -> tuple[str, str | None, str | None] | None:
    if coupon is None:
        return None
    return (coupon.state.value, None if coupon.amount is None else str(coupon.amount), coupon.code)


def _is_new_confirmed_coupon(current: Coupon | None, published: Coupon | None) -> bool:
    if current is None or not current.is_confirmed:
        return False
    if published is not None and published.is_confirmed:
        return _coupon_signature(current) != _coupon_signature(published)
    return True


def _has_evidence(evidence: Sequence[RepostEvidence], kind: RepostEvidenceType) -> bool:
    return any(item.evidence_type is kind for item in evidence)


def _select_baseline(
    history: Sequence[PublicationSnapshot], as_of: datetime
) -> PublicationSnapshot | None:
    valid = [
        snapshot
        for snapshot in history
        if snapshot.price.is_finite()
        and snapshot.price > 0
        and _to_utc(snapshot.published_at) <= as_of
    ]
    if not valid:
        return None
    return max(
        valid, key=lambda snapshot: (_to_utc(snapshot.published_at), snapshot.publication_id or "")
    )


def compute_repost(
    *,
    candidate_id: str,
    facts: RepostFacts,
    publication_history: Sequence[PublicationSnapshot],
    policy: RepostPolicy,
    as_of: datetime,
) -> RepostResult:
    """Compute the deterministic dedupe/repost decision.

    The function never mutates its inputs, never calls AI and is reproducible for
    the same facts, history and policy.
    """

    if not facts.current_price.is_finite() or facts.current_price <= 0:
        raise repost_input_invalid_error(
            "current_price deve ser maior que zero", context={"field": "current_price"}
        )
    if facts.deal_score is not None and not facts.deal_score.is_finite():
        raise repost_input_invalid_error(
            "deal_score deve ser finito", context={"field": "deal_score"}
        )

    reference_time = _to_utc(as_of)
    warnings: list[RepostWarning] = []
    baseline = _select_baseline(publication_history, reference_time)

    if baseline is None:
        if publication_history:
            warnings.append(
                RepostWarning(
                    code=WARNING_NO_COMPARABLE_HISTORY,
                    message=(
                        "Histórico de publicação sem referência comparável (preço inválido ou "
                        "publicação futura); repost tratado como primeira publicação"
                    ),
                    context={"history_count": len(publication_history)},
                )
            )
        return RepostResult(
            candidate_id=candidate_id,
            decision=RepostOutcome.ALLOWED,
            reason=RepostReason.FIRST_PUBLICATION,
            allowed=True,
            material_changes=(),
            publication=None,
            current_price=facts.current_price,
            observed_price_drop_percent=None,
            cooldown_expires_at=None,
            cooldown_expired=False,
            deal_score=facts.deal_score,
            policy=policy,
            warnings=tuple(warnings),
            as_of=reference_time,
        )

    published_at = _to_utc(baseline.published_at)
    cooldown_expires_at = published_at + timedelta(hours=policy.cooldown_hours)
    cooldown_expired = reference_time >= cooldown_expires_at

    observed_drop = _round_percent(
        (baseline.price - facts.current_price) / baseline.price * Decimal(100)
    )

    material_changes: list[MaterialChange] = []
    if observed_drop >= policy.price_drop_percent:
        material_changes.append(
            MaterialChange(
                change_type=MaterialChangeType.PRICE_DROP,
                detail={
                    "published_price": str(baseline.price),
                    "current_price": str(facts.current_price),
                    "observed_price_drop_percent": str(observed_drop),
                    "threshold_percent": str(policy.price_drop_percent),
                },
            )
        )

    published_coupon = baseline.coupon
    if _is_new_confirmed_coupon(facts.coupon, published_coupon):
        if _has_evidence(facts.evidence, RepostEvidenceType.COUPON):
            material_changes.append(
                MaterialChange(
                    change_type=MaterialChangeType.COUPON,
                    detail={
                        "coupon_state": facts.coupon.state.value if facts.coupon else None,
                        "coupon_amount": (
                            None
                            if facts.coupon is None or facts.coupon.amount is None
                            else str(facts.coupon.amount)
                        ),
                        "coupon_code": None if facts.coupon is None else facts.coupon.code,
                    },
                )
            )
        else:
            warnings.append(
                RepostWarning(
                    code=WARNING_COUPON_WITHOUT_EVIDENCE,
                    message=(
                        "Cupom confirmado diferente do publicado sem Evidence; não é tratado "
                        "como mudança material"
                    ),
                    context={"coupon_state": facts.coupon.state.value if facts.coupon else None},
                )
            )
    elif facts.coupon is not None and not facts.coupon.is_confirmed:
        warnings.append(
            RepostWarning(
                code=WARNING_COUPON_NOT_CONFIRMED,
                message=("Cupom informado não está CONFIRMED; não é tratado como mudança material"),
                context={"coupon_state": facts.coupon.state.value},
            )
        )

    current_conditions = _conditions_document(facts.conditions)
    published_conditions = _conditions_document(baseline.conditions)
    if current_conditions != published_conditions:
        if _has_evidence(facts.evidence, RepostEvidenceType.CONDITION):
            material_changes.append(
                MaterialChange(
                    change_type=MaterialChangeType.CONDITION,
                    detail={
                        "published_conditions": published_conditions,
                        "current_conditions": current_conditions,
                    },
                )
            )
        else:
            warnings.append(
                RepostWarning(
                    code=WARNING_CONDITION_WITHOUT_EVIDENCE,
                    message=(
                        "Condição material diferente da publicada sem Evidence; não é tratada "
                        "como mudança material"
                    ),
                    context={"current_conditions": current_conditions},
                )
            )

    decision = RepostOutcome.BLOCKED
    reason: RepostReason
    if material_changes:
        decision = RepostOutcome.ALLOWED
        reason = _reason_for(material_changes[0].change_type)
        warnings.extend(_material_warnings(material_changes))
    elif cooldown_expired:
        if facts.deal_score is not None and facts.deal_score >= policy.strong_deal_threshold:
            decision = RepostOutcome.ALLOWED
            reason = RepostReason.COOLDOWN_EXPIRED_STRONG_DEAL
        else:
            reason = RepostReason.DEAL_NOT_STRONG
            warnings.append(
                RepostWarning(
                    code=WARNING_DEAL_NOT_STRONG,
                    message=(
                        "Cooldown vencido mas Deal não é forte o suficiente para repost; "
                        "oferta sem mudança material bloqueada"
                    ),
                    context={
                        "deal_score": None if facts.deal_score is None else str(facts.deal_score),
                        "strong_deal_threshold": str(policy.strong_deal_threshold),
                    },
                )
            )
    else:
        reason = RepostReason.DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE
        warnings.append(
            RepostWarning(
                code=WARNING_COOLDOWN_ACTIVE,
                message="Cooldown ativo e sem mudança material; repost bloqueado",
                context={"cooldown_expires_at": cooldown_expires_at.isoformat()},
            )
        )
        warnings.append(
            RepostWarning(
                code=WARNING_DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE,
                message="Duplicação sem mudança significativa; repost bloqueado",
                context={},
            )
        )

    return RepostResult(
        candidate_id=candidate_id,
        decision=decision,
        reason=reason,
        allowed=decision is RepostOutcome.ALLOWED,
        material_changes=tuple(material_changes),
        publication=baseline,
        current_price=facts.current_price,
        observed_price_drop_percent=observed_drop,
        cooldown_expires_at=cooldown_expires_at,
        cooldown_expired=cooldown_expired,
        deal_score=facts.deal_score,
        policy=policy,
        warnings=tuple(warnings),
        as_of=reference_time,
    )


def _reason_for(change_type: MaterialChangeType) -> RepostReason:
    if change_type is MaterialChangeType.PRICE_DROP:
        return RepostReason.MATERIAL_PRICE_DROP
    if change_type is MaterialChangeType.COUPON:
        return RepostReason.MATERIAL_COUPON
    return RepostReason.MATERIAL_CONDITION


def _material_warnings(changes: Sequence[MaterialChange]) -> list[RepostWarning]:
    warnings: list[RepostWarning] = []
    for change in changes:
        if change.change_type is MaterialChangeType.PRICE_DROP:
            warnings.append(
                RepostWarning(
                    code=WARNING_MATERIAL_PRICE_DROP,
                    message="Queda de preço desde a publicação libera o repost",
                    context=dict(change.detail),
                )
            )
        elif change.change_type is MaterialChangeType.COUPON:
            warnings.append(
                RepostWarning(
                    code=WARNING_MATERIAL_COUPON,
                    message="Novo cupom material com Evidence libera o repost",
                    context=dict(change.detail),
                )
            )
        else:
            warnings.append(
                RepostWarning(
                    code=WARNING_MATERIAL_CONDITION,
                    message="Nova condição material com Evidence libera o repost",
                    context=dict(change.detail),
                )
            )
    return warnings


def build_repost_evidence(
    *,
    decision_id: str,
    result: RepostResult,
    captured_at: datetime,
    make_id: Callable[[str], str],
    supplied_evidence: Sequence[RepostEvidence] = (),
) -> tuple[Evidence, ...]:
    """Build the Evidence rows that sustain the decision (AUT-029, AUT-077)."""

    captured = _to_utc(captured_at)
    facts: list[tuple[str, str]] = [
        (EVIDENCE_FIELD_DECISION, result.decision.value),
        (EVIDENCE_FIELD_REASON, result.reason.value),
        (EVIDENCE_FIELD_CURRENT_PRICE, str(result.current_price)),
        (EVIDENCE_FIELD_POLICY, result.policy.policy_version),
    ]
    if result.publication is not None:
        facts.append((EVIDENCE_FIELD_PUBLISHED_PRICE, str(result.publication.price)))
    if result.observed_price_drop_percent is not None:
        facts.append(
            (EVIDENCE_FIELD_OBSERVED_PRICE_DROP_PERCENT, str(result.observed_price_drop_percent))
        )
    if result.cooldown_expires_at is not None:
        facts.append((EVIDENCE_FIELD_COOLDOWN_EXPIRES_AT, result.cooldown_expires_at.isoformat()))
    if result.deal_score is not None:
        facts.append((EVIDENCE_FIELD_DEAL_SCORE, str(result.deal_score)))
    for change in result.material_changes:
        facts.append(
            (
                EVIDENCE_FIELD_MATERIAL_CHANGE,
                f"{change.change_type.value}:{json.dumps(dict(change.detail), sort_keys=True)}",
            )
        )

    rows = [
        Evidence(
            id=make_id("evd"),
            entity_type=ENTITY_REPOST_DECISION,
            entity_id=decision_id,
            field_name=field_name,
            value=value,
            source_type=EVIDENCE_SOURCE_REPOST_REVIEW,
            captured_at=captured,
        )
        for field_name, value in facts
    ]
    for item in supplied_evidence:
        field_name = (
            EVIDENCE_FIELD_COUPON_EVIDENCE
            if item.evidence_type is RepostEvidenceType.COUPON
            else EVIDENCE_FIELD_CONDITION_EVIDENCE
        )
        rows.append(
            Evidence(
                id=make_id("evd"),
                entity_type=ENTITY_REPOST_DECISION,
                entity_id=decision_id,
                field_name=field_name,
                value=f"{item.reference_id}:{item.field}={item.value}",
                source_type=item.source,
                captured_at=captured,
            )
        )
    return tuple(rows)


def _content_hash(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_decimal(value: Any, *, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise repost_policy_invalid_error(
            "valor deve ser decimal, não booleano", context={"field": field_name}
        )
    if isinstance(value, float):
        raise repost_policy_invalid_error(
            "valor deve ser decimal/inteiro, não float binário", context={"field": field_name}
        )
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, str):
        try:
            amount = Decimal(value.strip())
        except InvalidOperation as exc:
            raise repost_policy_invalid_error(
                "valor inválido", context={"field": field_name}
            ) from exc
    else:
        raise repost_policy_invalid_error("valor inválido", context={"field": field_name})
    if not amount.is_finite() or amount < 0:
        raise repost_policy_invalid_error(
            "valor deve ser finito e >= 0", context={"field": field_name}
        )
    return amount


def _to_hours(value: Any) -> int:
    if isinstance(value, bool):
        raise repost_policy_invalid_error("cooldown_hours não pode ser booleano")
    if isinstance(value, int):
        hours = value
    elif isinstance(value, str) and value.strip().isdigit():
        hours = int(value.strip())
    else:
        raise repost_policy_invalid_error(
            "cooldown_hours deve ser um inteiro de horas", context={"field": "cooldown_hours"}
        )
    if hours <= 0:
        raise repost_policy_invalid_error(
            "cooldown_hours deve ser maior que zero", context={"field": "cooldown_hours"}
        )
    return hours


def build_repost_policy(document: Mapping[str, Any]) -> RepostPolicy:
    """Build and validate the repost policy from a plain document.

    Raises :class:`RepostPolicyInvalidError` (``RAD-CFG-009``) on an unsupported
    schema, a missing version, a non-positive cooldown, a negative threshold or an
    out-of-range strong-deal threshold. A document without an explicit cooldown or
    price-drop threshold falls back to the approved baseline (72h / 10%).
    """

    if not isinstance(document, Mapping):
        raise repost_policy_invalid_error("Policy deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != REPOST_POLICY_SCHEMA_VERSION:
        raise repost_policy_invalid_error(
            "schema_version de policy não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("policy_version") or "").strip()
    if not version:
        raise repost_policy_invalid_error("policy_version é obrigatório")

    cooldown_hours = _to_hours(document.get("cooldown_hours", 72))
    price_drop_percent = _to_decimal(
        document.get("price_drop_percent", 10), field_name="price_drop_percent"
    )
    strong_deal_threshold = _to_decimal(
        document.get("strong_deal_threshold", 80), field_name="strong_deal_threshold"
    )
    if strong_deal_threshold > 100:
        raise repost_policy_invalid_error(
            "strong_deal_threshold deve estar entre 0 e 100",
            context={"field": "strong_deal_threshold"},
        )

    normalized = {
        "schema_version": REPOST_POLICY_SCHEMA_VERSION,
        "policy_version": version,
        "cooldown_hours": cooldown_hours,
        "price_drop_percent": str(price_drop_percent),
        "strong_deal_threshold": str(strong_deal_threshold),
    }
    return RepostPolicy(
        policy_version=version,
        content_hash=_content_hash(normalized),
        cooldown_hours=cooldown_hours,
        price_drop_percent=price_drop_percent,
        strong_deal_threshold=strong_deal_threshold,
    )


#: Approved baseline policy (RDR-033).
#:
#: ``docs/05_SCORING_ENGINE.md`` freezes an initial cooldown of ``72h`` and a
#: price drop of ``>= 10%``; the strong-deal floor is the SDD Deal threshold of
#: ``>= 80``. All three remain configurable, so the baseline is the approved
#: reference rather than a hardcoded rule.
APPROVED_REPOST_POLICY_DOCUMENT: dict[str, Any] = {
    "schema_version": REPOST_POLICY_SCHEMA_VERSION,
    "policy_version": "repost-policy-1.0",
    "cooldown_hours": 72,
    "price_drop_percent": "10",
    "strong_deal_threshold": "80",
}

#: The approved baseline used when no operator file is configured.
APPROVED_REPOST_POLICY: RepostPolicy = build_repost_policy(APPROVED_REPOST_POLICY_DOCUMENT)


__all__ = [
    "APPROVED_REPOST_POLICY",
    "APPROVED_REPOST_POLICY_DOCUMENT",
    "ENTITY_REPOST_DECISION",
    "EVIDENCE_FIELD_CONDITION_EVIDENCE",
    "EVIDENCE_FIELD_COOLDOWN_EXPIRES_AT",
    "EVIDENCE_FIELD_COUPON_EVIDENCE",
    "EVIDENCE_FIELD_CURRENT_PRICE",
    "EVIDENCE_FIELD_DEAL_SCORE",
    "EVIDENCE_FIELD_DECISION",
    "EVIDENCE_FIELD_MATERIAL_CHANGE",
    "EVIDENCE_FIELD_OBSERVED_PRICE_DROP_PERCENT",
    "EVIDENCE_FIELD_POLICY",
    "EVIDENCE_FIELD_PUBLISHED_PRICE",
    "EVIDENCE_FIELD_REASON",
    "EVIDENCE_SOURCE_REPOST_INPUT",
    "EVIDENCE_SOURCE_REPOST_REVIEW",
    "REPOST_ENGINE_VERSION",
    "REPOST_INPUT_INVALID",
    "REPOST_POLICY_INVALID",
    "REPOST_POLICY_SCHEMA_VERSION",
    "REPOST_SCHEMA_VERSION",
    "WARNING_CONDITION_WITHOUT_EVIDENCE",
    "WARNING_COOLDOWN_ACTIVE",
    "WARNING_COUPON_NOT_CONFIRMED",
    "WARNING_COUPON_WITHOUT_EVIDENCE",
    "WARNING_DEAL_NOT_STRONG",
    "WARNING_DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE",
    "WARNING_MATERIAL_CONDITION",
    "WARNING_MATERIAL_COUPON",
    "WARNING_MATERIAL_PRICE_DROP",
    "WARNING_NO_COMPARABLE_HISTORY",
    "MaterialChange",
    "MaterialChangeType",
    "PublicationSnapshot",
    "RepostDecisionRecord",
    "RepostError",
    "RepostEvidence",
    "RepostEvidenceType",
    "RepostFacts",
    "RepostOutcome",
    "RepostPolicy",
    "RepostPolicyInvalidError",
    "RepostReason",
    "RepostResult",
    "RepostWarning",
    "build_repost_evidence",
    "build_repost_policy",
    "compute_repost",
    "repost_input_invalid_error",
    "repost_policy_invalid_error",
]
