"""Deterministic Allowed Claims engine (RDR-032).

Commercial claims are produced by the backend, never by AI (AUT-063, AUT-076,
AUT-084). This module implements the *Allowed Claims* of
``docs/05_SCORING_ENGINE.md``: given an immutable Evaluation and the persisted
evidence of a Candidate (the ``Offer`` and its append-only
``PriceObservation`` history, RDR-013), it returns the versioned claims that may
appear in editorial content, each one carrying traceable provenance (AUT-077,
AUT-292). The module is framework-free (no FastAPI/SQLAlchemy/Chrome) so the
domain stays independent from infrastructure (AUT-397), and the AI cannot create
or alter a claim.

Three rules are load-bearing:

* ``LOWEST_OBSERVED_30D`` is only produced when the own price history **covers**
  the whole 30-day window; a since-we-started minimum is not a 30-day minimum and
  is therefore omitted with an explicit warning (acceptance criterion 2);
* a ``LIKELY``/``UNKNOWN``/``NOT_APPLICABLE`` coupon and the isolated
  struck-through marketplace price never become proof: only a ``CONFIRMED``
  coupon yields ``CONFIRMED_COUPON`` and nothing here reads ``original_price`` as
  a reference (AUT-048, ``docs/05``);
* an unsupported claim is omitted (and reported in ``omitted_claims``) instead of
  being invented, so the frontend/AI can only use claims the backend sustains.

The result is read-only and deterministic; it adds no store of its own because it
is a pure function of the immutable Evaluation plus the append-only evidence
already persisted (RDR-016, RDR-013).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from radar.domain.errors import RadarError, RadarException
from radar.domain.price_opportunity import Coupon

#: Version of the public Allowed Claims contract.
ALLOWED_CLAIMS_SCHEMA_VERSION = "1.0"

#: Version of the deterministic engine stored alongside the result (AUT-065).
ALLOWED_CLAIMS_ENGINE_VERSION = "allowed-claims-1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
EVALUATION_NOT_FOUND = "RAD-CAP-013"
ALLOWED_CLAIMS_INPUT_INVALID = "RAD-CAP-014"

#: Window of the ``LOWEST_OBSERVED_30D`` claim (``docs/05_SCORING_ENGINE.md``).
LOWEST_OBSERVED_WINDOW_DAYS = 30

#: Minimum number of observations required to sustain the 30-day claim. The
#: window is only truthful when the series brackets it (an observation at or
#: before the window start plus one inside it); a single recent point is a
#: ``since we started`` minimum, not a 30-day one.
MIN_HISTORY_OBSERVATIONS = 2

#: Warning codes emitted as explicit, non-fatal gaps.
WARNING_NO_PRICE_HISTORY = "NO_PRICE_HISTORY"
WARNING_LOWEST_30D_HISTORY_INSUFFICIENT = "LOWEST_OBSERVED_30D_HISTORY_INSUFFICIENT"
WARNING_COUPON_NOT_CONFIRMED = "COUPON_NOT_CONFIRMED"
WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF = "STRUCK_THROUGH_PRICE_NOT_PROOF"
WARNING_SALES_COUNT_UNAVAILABLE = "SALES_COUNT_UNAVAILABLE"

#: Omission reasons reported for claims without enough support.
OMISSION_NO_PRIOR_OBSERVATION = "NO_PRIOR_OBSERVATION"
OMISSION_NO_PRICE_DROP = "NO_PRICE_DROP"
OMISSION_HISTORY_INSUFFICIENT = "HISTORY_INSUFFICIENT"
OMISSION_COUPON_NOT_CONFIRMED = "COUPON_NOT_CONFIRMED"
OMISSION_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"

#: Claims that must never be produced (``docs/06_AI_ENGINE.md``).
FORBIDDEN_CLAIMS: tuple[str, ...] = (
    "BEST_PRICE_ON_THE_INTERNET",
    "LAST_UNITS",
    "WILL_SELL_OUT",
    "GUARANTEED_ORIGINAL",
    "PERSONAL_EXPERIENCE",
    "UNVERIFIED_COUPON",
)


class ClaimType(StrEnum):
    """Commercial claims supported by the backend (``docs/05_SCORING_ENGINE.md``)."""

    CURRENT_PRICE = "CURRENT_PRICE"
    PREVIOUS_OBSERVED_PRICE = "PREVIOUS_OBSERVED_PRICE"
    PRICE_DROP_PERCENT = "PRICE_DROP_PERCENT"
    LOWEST_OBSERVED_30D = "LOWEST_OBSERVED_30D"
    SALES_COUNT = "SALES_COUNT"
    CONFIRMED_COUPON = "CONFIRMED_COUPON"


class ClaimUnit(StrEnum):
    """Unit of a claim value, so a renderer never reinterprets it."""

    MONEY = "money"
    PERCENT = "percent"
    COUNT = "count"
    COUPON = "coupon"


class ClaimEvidenceType(StrEnum):
    """Kind of persisted fact that sustains a claim."""

    OFFER = "offer"
    PRICE_OBSERVATION = "price_observation"


class AllowedClaimsError(RadarException):
    """Raised when Allowed Claims cannot be produced for a Candidate."""


def evaluation_not_found_error(
    candidate_id: str, *, evaluation_id: str | None = None
) -> AllowedClaimsError:
    """Build the structured error for a missing Evaluation."""

    context: dict[str, Any] = {"candidate_id": candidate_id}
    if evaluation_id is not None:
        context["evaluation_id"] = evaluation_id
    return AllowedClaimsError(
        RadarError(
            code=EVALUATION_NOT_FOUND,
            message="Evaluation não encontrada para o Candidate",
            retryable=False,
            action="Avaliar o Candidate antes de consultar os claims permitidos",
            context=context,
        )
    )


def allowed_claims_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> AllowedClaimsError:
    """Build the structured error for invalid Allowed Claims conditions."""

    return AllowedClaimsError(
        RadarError(
            code=ALLOWED_CLAIMS_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir a condição informada e consultar novamente",
            context=dict(context or {}),
        )
    )


@dataclass(frozen=True, slots=True)
class ClaimPriceFact:
    """One append-only price observation available as claim evidence (RDR-013)."""

    observation_id: str
    price: Decimal
    observed_at: datetime
    source: str
    correlation_id: str
    raw_capture_id: str


@dataclass(frozen=True, slots=True)
class ClaimOfferFacts:
    """Persisted Offer facts that sustain the claims of one Candidate."""

    offer_id: str
    current_price: Decimal
    observed_at: datetime
    source: str
    correlation_id: str
    raw_capture_id: str
    sales_count: int | None = None
    coupon: Coupon | None = None
    original_price: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ClaimEvidence:
    """Traceable provenance of one claim (AUT-077)."""

    evidence_type: ClaimEvidenceType
    reference_id: str
    field: str
    value: str
    observed_at: datetime
    source: str
    correlation_id: str
    raw_capture_id: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "evidence_type": self.evidence_type.value,
            "reference_id": self.reference_id,
            "field": self.field,
            "value": self.value,
            "observed_at": _to_utc(self.observed_at).isoformat(),
            "source": self.source,
            "correlation_id": self.correlation_id,
            "raw_capture_id": self.raw_capture_id,
        }


@dataclass(frozen=True, slots=True)
class AllowedClaim:
    """A commercial statement the backend sustains with evidence."""

    claim_type: ClaimType
    value: str
    unit: ClaimUnit
    evidence: tuple[ClaimEvidence, ...]

    def to_contract(self) -> dict[str, Any]:
        return {
            "claim_type": self.claim_type.value,
            "value": self.value,
            "unit": self.unit.value,
            "evidence": [item.to_contract() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class OmittedClaim:
    """A claim that was blocked because its support is missing."""

    claim_type: ClaimType
    reason_code: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "claim_type": self.claim_type.value,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class AllowedClaimsWarning:
    """Explicit, non-fatal gap emitted by the engine."""

    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class AllowedClaimsResult:
    """Queryable, versioned allowed claims bound to one Evaluation version."""

    candidate_id: str
    evaluation_id: str
    evaluation_decision: str
    claims: tuple[AllowedClaim, ...]
    omitted_claims: tuple[OmittedClaim, ...]
    warnings: tuple[AllowedClaimsWarning, ...]
    as_of: datetime

    def claim(self, claim_type: ClaimType) -> AllowedClaim | None:
        """Return one allowed claim by type, or ``None`` when it was omitted."""

        for claim in self.claims:
            if claim.claim_type is claim_type:
                return claim
        return None

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": ALLOWED_CLAIMS_SCHEMA_VERSION,
            "status": "OK",
            "engine_version": ALLOWED_CLAIMS_ENGINE_VERSION,
            "candidate_id": self.candidate_id,
            "evaluation_id": self.evaluation_id,
            "evaluation_decision": self.evaluation_decision,
            "as_of": _to_utc(self.as_of).isoformat(),
            "claim_count": len(self.claims),
            "claims": [claim.to_contract() for claim in self.claims],
            "omitted_claims": [omitted.to_contract() for omitted in self.omitted_claims],
            "forbidden_claims": list(FORBIDDEN_CLAIMS),
            "warnings": [warning.to_contract() for warning in self.warnings],
        }


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _round_percent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _offer_evidence(offer: ClaimOfferFacts, *, field: str, value: str) -> ClaimEvidence:
    return ClaimEvidence(
        evidence_type=ClaimEvidenceType.OFFER,
        reference_id=offer.offer_id,
        field=field,
        value=value,
        observed_at=_to_utc(offer.observed_at),
        source=offer.source,
        correlation_id=offer.correlation_id,
        raw_capture_id=offer.raw_capture_id,
    )


def _observation_evidence(fact: ClaimPriceFact, *, field: str) -> ClaimEvidence:
    return ClaimEvidence(
        evidence_type=ClaimEvidenceType.PRICE_OBSERVATION,
        reference_id=fact.observation_id,
        field=field,
        value=str(fact.price),
        observed_at=_to_utc(fact.observed_at),
        source=fact.source,
        correlation_id=fact.correlation_id,
        raw_capture_id=fact.raw_capture_id,
    )


def compute_allowed_claims(
    *,
    candidate_id: str,
    evaluation_id: str,
    evaluation_decision: str,
    offer: ClaimOfferFacts,
    history: Sequence[ClaimPriceFact] = (),
) -> AllowedClaimsResult:
    """Produce the evidence-backed claims of one Candidate's Evaluation.

    ``offer.observed_at`` is the instant of the Candidate's current condition;
    observations at or after it are not a history reference. The function never
    mutates its inputs, never calls AI and is reproducible for the same facts.
    """

    as_of = _to_utc(offer.observed_at)
    # Non-positive observations and future ones are invalid as evidence and are
    # ignored instead of becoming a made-up reference.
    ordered = sorted(
        (fact for fact in history if fact.price > 0 and _to_utc(fact.observed_at) <= as_of),
        key=lambda fact: (_to_utc(fact.observed_at), fact.observation_id),
    )
    prior = [fact for fact in ordered if _to_utc(fact.observed_at) < as_of]
    reference = prior[-1] if prior else None

    claims: list[AllowedClaim] = []
    omitted: list[OmittedClaim] = []
    warnings: list[AllowedClaimsWarning] = []

    # --- CURRENT_PRICE (always backed by the persisted Offer) ---------------
    current_evidence = _offer_evidence(offer, field="current_price", value=str(offer.current_price))
    claims.append(
        AllowedClaim(
            claim_type=ClaimType.CURRENT_PRICE,
            value=str(offer.current_price),
            unit=ClaimUnit.MONEY,
            evidence=(current_evidence,),
        )
    )

    # --- PREVIOUS_OBSERVED_PRICE / PRICE_DROP_PERCENT -----------------------
    if reference is None:
        omitted.append(
            OmittedClaim(ClaimType.PREVIOUS_OBSERVED_PRICE, OMISSION_NO_PRIOR_OBSERVATION)
        )
        omitted.append(OmittedClaim(ClaimType.PRICE_DROP_PERCENT, OMISSION_NO_PRIOR_OBSERVATION))
        warnings.append(
            AllowedClaimsWarning(
                code=WARNING_NO_PRICE_HISTORY,
                message=(
                    "Sem observação anterior própria; claims de histórico e queda são "
                    "omitidos em vez de inventar referência"
                ),
                context={"prior_observation_count": 0},
            )
        )
    else:
        reference_evidence = _observation_evidence(reference, field="price")
        claims.append(
            AllowedClaim(
                claim_type=ClaimType.PREVIOUS_OBSERVED_PRICE,
                value=str(reference.price),
                unit=ClaimUnit.MONEY,
                evidence=(reference_evidence,),
            )
        )
        drop_percent = _round_percent(
            (reference.price - offer.current_price) / reference.price * Decimal(100)
        )
        if drop_percent > 0:
            claims.append(
                AllowedClaim(
                    claim_type=ClaimType.PRICE_DROP_PERCENT,
                    value=str(drop_percent),
                    unit=ClaimUnit.PERCENT,
                    evidence=(current_evidence, reference_evidence),
                )
            )
        else:
            omitted.append(OmittedClaim(ClaimType.PRICE_DROP_PERCENT, OMISSION_NO_PRICE_DROP))

    # --- LOWEST_OBSERVED_30D ------------------------------------------------
    window_start = as_of - timedelta(days=LOWEST_OBSERVED_WINDOW_DAYS)
    in_window = [fact for fact in ordered if _to_utc(fact.observed_at) >= window_start]
    oldest = ordered[0] if ordered else None
    window_covered = (
        oldest is not None
        and len(ordered) >= MIN_HISTORY_OBSERVATIONS
        and _to_utc(oldest.observed_at) <= window_start
        and bool(in_window)
    )
    if window_covered:
        assert oldest is not None
        minimum = min([fact.price for fact in in_window] + [offer.current_price])
        minimum_evidence: list[ClaimEvidence] = []
        if minimum == offer.current_price:
            minimum_evidence.append(current_evidence)
        minimum_evidence.extend(
            _observation_evidence(fact, field="price")
            for fact in in_window
            if fact.price == minimum
        )
        minimum_evidence.append(_observation_evidence(oldest, field="coverage"))
        claims.append(
            AllowedClaim(
                claim_type=ClaimType.LOWEST_OBSERVED_30D,
                value=str(minimum),
                unit=ClaimUnit.MONEY,
                evidence=tuple(minimum_evidence),
            )
        )
    else:
        omitted.append(OmittedClaim(ClaimType.LOWEST_OBSERVED_30D, OMISSION_HISTORY_INSUFFICIENT))
        warnings.append(
            AllowedClaimsWarning(
                code=WARNING_LOWEST_30D_HISTORY_INSUFFICIENT,
                message=(
                    "Histórico próprio não cobre a janela de 30 dias; "
                    "LOWEST_OBSERVED_30D é omitido para não sustentar afirmação falsa"
                ),
                context={
                    "observation_count": len(ordered),
                    "window_days": LOWEST_OBSERVED_WINDOW_DAYS,
                },
            )
        )

    # --- SALES_COUNT --------------------------------------------------------
    if offer.sales_count is not None and offer.sales_count >= 0:
        claims.append(
            AllowedClaim(
                claim_type=ClaimType.SALES_COUNT,
                value=str(offer.sales_count),
                unit=ClaimUnit.COUNT,
                evidence=(
                    _offer_evidence(offer, field="sales_count", value=str(offer.sales_count)),
                ),
            )
        )
    else:
        omitted.append(OmittedClaim(ClaimType.SALES_COUNT, OMISSION_DATA_UNAVAILABLE))
        warnings.append(
            AllowedClaimsWarning(
                code=WARNING_SALES_COUNT_UNAVAILABLE,
                message="sales_count ausente; claim SALES_COUNT é omitido",
                context={},
            )
        )

    # --- CONFIRMED_COUPON ---------------------------------------------------
    coupon = offer.coupon
    if coupon is None:
        omitted.append(OmittedClaim(ClaimType.CONFIRMED_COUPON, OMISSION_DATA_UNAVAILABLE))
    elif not coupon.is_confirmed:
        omitted.append(OmittedClaim(ClaimType.CONFIRMED_COUPON, OMISSION_COUPON_NOT_CONFIRMED))
        warnings.append(
            AllowedClaimsWarning(
                code=WARNING_COUPON_NOT_CONFIRMED,
                message=("Cupom provável/desconhecido não é prova; CONFIRMED_COUPON é omitido"),
                context={"coupon_state": coupon.state.value},
            )
        )
    else:
        if coupon.code:
            coupon_value: str | None = coupon.code
        elif coupon.amount is not None and coupon.amount > 0:
            coupon_value = str(coupon.amount)
        else:
            coupon_value = None
        if coupon_value is None:
            omitted.append(OmittedClaim(ClaimType.CONFIRMED_COUPON, OMISSION_DATA_UNAVAILABLE))
        else:
            claims.append(
                AllowedClaim(
                    claim_type=ClaimType.CONFIRMED_COUPON,
                    value=coupon_value,
                    unit=ClaimUnit.COUPON,
                    evidence=(_offer_evidence(offer, field="coupon", value=coupon_value),),
                )
            )

    # --- Struck-through price is never proof --------------------------------
    if offer.original_price is not None:
        warnings.append(
            AllowedClaimsWarning(
                code=WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF,
                message=("Preço riscado do marketplace não é prova de vantagem e não vira claim"),
                context={"original_price": str(offer.original_price)},
            )
        )

    return AllowedClaimsResult(
        candidate_id=candidate_id,
        evaluation_id=evaluation_id,
        evaluation_decision=evaluation_decision,
        claims=tuple(claims),
        omitted_claims=tuple(omitted),
        warnings=tuple(warnings),
        as_of=as_of,
    )


__all__ = [
    "ALLOWED_CLAIMS_ENGINE_VERSION",
    "ALLOWED_CLAIMS_INPUT_INVALID",
    "ALLOWED_CLAIMS_SCHEMA_VERSION",
    "EVALUATION_NOT_FOUND",
    "FORBIDDEN_CLAIMS",
    "LOWEST_OBSERVED_WINDOW_DAYS",
    "MIN_HISTORY_OBSERVATIONS",
    "OMISSION_COUPON_NOT_CONFIRMED",
    "OMISSION_DATA_UNAVAILABLE",
    "OMISSION_HISTORY_INSUFFICIENT",
    "OMISSION_NO_PRICE_DROP",
    "OMISSION_NO_PRIOR_OBSERVATION",
    "WARNING_COUPON_NOT_CONFIRMED",
    "WARNING_LOWEST_30D_HISTORY_INSUFFICIENT",
    "WARNING_NO_PRICE_HISTORY",
    "WARNING_SALES_COUNT_UNAVAILABLE",
    "WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF",
    "AllowedClaim",
    "AllowedClaimsError",
    "AllowedClaimsResult",
    "AllowedClaimsWarning",
    "ClaimEvidence",
    "ClaimEvidenceType",
    "ClaimOfferFacts",
    "ClaimPriceFact",
    "ClaimType",
    "ClaimUnit",
    "OmittedClaim",
    "allowed_claims_input_invalid_error",
    "compute_allowed_claims",
    "evaluation_not_found_error",
]
