"""Deterministic Price Opportunity breakdown (RDR-023).

This module implements the *Price Opportunity* component of the Deal Score
described in ``docs/05_SCORING_ENGINE.md``. It consumes the append-only price
history (RDR-013), the Candidate's confirmed commercial conditions (coupon,
shipping) and comparable evidence, and returns an explainable, versioned
breakdown. The module is framework-free (no FastAPI/SQLAlchemy/Chrome) so the
domain stays independent from infrastructure (AUT-397).

Two rules are load-bearing:

* the struck-through marketplace price (``original_price``) is **not** proof of
  advantage (AUT-048): it never becomes a history reference and it never reduces
  the effective price;
* only a ``CONFIRMED`` coupon reduces the effective price, and the SDD does not
  calibrate score ranges for the ``Coupon / Final Price`` and ``Shipping
  Impact`` components. Those components are therefore reported as explicit
  calibration gaps with ``score=None`` instead of an invented number (AUT-045,
  AUT-049). The returned ``price_opportunity`` is a partial score computed over
  the approved components only and carries ``fully_calibrated=false``.

Missing data never becomes an arbitrary zero: insufficient history and an
absent comparison reference use the approved neutral value ``50`` and emit a
warning that the Confidence Engine (RDR-029) consumes (AUT-049, AUT-057).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from radar.domain.errors import RadarError, RadarException

#: Version of the public Price Opportunity contract.
PRICE_OPPORTUNITY_SCHEMA_VERSION = "1.0"

#: Scoring version stored alongside the breakdown (``docs/05_SCORING_ENGINE.md``).
PRICE_OPPORTUNITY_SCORING_VERSION = "price-opportunity-1.0"

#: Error code (see ``docs/ERROR_CATALOG.md``).
PRICE_OPPORTUNITY_INPUT_INVALID = "RAD-CAP-008"

#: Approved component weights, frozen by ``docs/05_SCORING_ENGINE.md``.
WEIGHT_HISTORICAL_POSITION = 45
WEIGHT_RECENT_PRICE_DROP = 20
WEIGHT_MARKETPLACE_COMPARISON = 20
WEIGHT_COUPON_FINAL_PRICE = 10
WEIGHT_SHIPPING_IMPACT = 5

#: Neutral value used when a component has no reliable evidence.
NEUTRAL_SCORE = 50

#: Preferred history window in days (``docs/05_SCORING_ENGINE.md``: ``30d >
#: lifetime > 7d``). The 7-day window is a strict subset of both the 30-day and
#: the lifetime windows, so it never carries evidence they lack.
PREFERRED_HISTORY_WINDOW_DAYS = 30

#: Warning codes. ``SHORT_PRICE_HISTORY``/``UNKNOWN_SHIPPING``/
#: ``COUPON_NOT_CONFIRMED`` are Soft Rules from ``docs/05_SCORING_ENGINE.md``
#: that reduce Confidence.
WARNING_SHORT_PRICE_HISTORY = "SHORT_PRICE_HISTORY"
WARNING_NO_PRICE_REFERENCE = "NO_PRICE_REFERENCE"
WARNING_NO_MARKETPLACE_REFERENCE = "NO_MARKETPLACE_REFERENCE"
WARNING_UNKNOWN_SHIPPING = "UNKNOWN_SHIPPING"
WARNING_COUPON_NOT_CONFIRMED = "COUPON_NOT_CONFIRMED"
WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF = "STRUCK_THROUGH_PRICE_NOT_PROOF"
WARNING_CALIBRATION_REQUIRED = "PRICE_OPPORTUNITY_CALIBRATION_REQUIRED"


class CouponState(StrEnum):
    """Coupon confidence states (``docs/05_SCORING_ENGINE.md``)."""

    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PriceOpportunityComponentName(StrEnum):
    """Canonical component names of the Price Opportunity breakdown."""

    HISTORICAL_POSITION = "historical_position"
    RECENT_PRICE_DROP = "recent_price_drop"
    MARKETPLACE_COMPARISON = "marketplace_comparison"
    COUPON_FINAL_PRICE = "coupon_final_price"
    SHIPPING_IMPACT = "shipping_impact"


class PriceOpportunityError(RadarException):
    """Raised when Price Opportunity inputs cannot be evaluated."""


def price_opportunity_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> PriceOpportunityError:
    """Build the structured error for invalid Price Opportunity inputs."""

    return PriceOpportunityError(
        RadarError(
            code=PRICE_OPPORTUNITY_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir os parâmetros da avaliação de preço e consultar novamente",
            context=dict(context or {}),
        )
    )


@dataclass(frozen=True, slots=True)
class Coupon:
    """Coupon condition attached to an Offer.

    ``amount`` is only meaningful for ``CONFIRMED``; the other states never
    reduce the effective price or become a claim (AUT-048, ``docs/05``).
    """

    state: CouponState = CouponState.UNKNOWN
    amount: Decimal | None = None
    code: str | None = None

    @property
    def is_confirmed(self) -> bool:
        return self.state is CouponState.CONFIRMED

    def applied_amount(self) -> Decimal | None:
        """Return the amount that may reduce the effective price, if any."""

        if self.is_confirmed and self.amount is not None and self.amount > 0:
            return self.amount
        return None


@dataclass(frozen=True, slots=True)
class PriceHistoryFact:
    """One append-only price observation used by the calculation."""

    price: Decimal
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ComparableEvidence:
    """Verified comparable price for the same Product (cross-marketplace).

    Product equivalence is owned by RDR-031 (TKT-10); this value is only
    consumed when it has already been established as comparable.
    """

    price: Decimal
    marketplace: str | None = None


@dataclass(frozen=True, slots=True)
class PriceOpportunityComponent:
    """One explainable component of the Price Opportunity breakdown."""

    name: PriceOpportunityComponentName
    weight: int
    score: int | None
    calibrated: bool
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name.value,
            "weight": self.weight,
            "score": self.score,
            "calibrated": self.calibrated,
        }
        if self.detail:
            payload["detail"] = dict(self.detail)
        return payload


@dataclass(frozen=True, slots=True)
class PriceOpportunityWarning:
    """Explicit, non-fatal gap emitted by the calculation."""

    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class PriceOpportunityResult:
    """Queryable, versioned Price Opportunity for one Candidate."""

    candidate_id: str
    price_opportunity: int | None
    fully_calibrated: bool
    weight_covered: int
    effective_price: Decimal | None
    current_price: Decimal
    original_price: Decimal | None
    shipping_cost: Decimal | None
    shipping_known: bool
    coupon: Coupon
    coupon_applied: bool
    observation_count: int
    prior_observation_count: int
    history_source: str
    history_window_days: int | None
    components: tuple[PriceOpportunityComponent, ...]
    warnings: tuple[PriceOpportunityWarning, ...]
    as_of: datetime

    def component(self, name: PriceOpportunityComponentName) -> PriceOpportunityComponent:
        """Return one component by name (every component is always present)."""

        for item in self.components:
            if item.name is name:
                return item
        raise KeyError(name.value)

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": PRICE_OPPORTUNITY_SCHEMA_VERSION,
            "status": "EVALUATED",
            "candidate_id": self.candidate_id,
            "price_opportunity": self.price_opportunity,
            "fully_calibrated": self.fully_calibrated,
            "weight_covered": self.weight_covered,
            "scoring_version": PRICE_OPPORTUNITY_SCORING_VERSION,
            "as_of": _to_utc(self.as_of).isoformat(),
            "current_price": str(self.current_price),
            "original_price": None if self.original_price is None else str(self.original_price),
            "effective_price": None if self.effective_price is None else str(self.effective_price),
            "shipping_cost": None if self.shipping_cost is None else str(self.shipping_cost),
            "shipping_known": self.shipping_known,
            "coupon": {
                "code": self.coupon.code,
                "state": self.coupon.state.value,
                "amount": None if self.coupon.amount is None else str(self.coupon.amount),
                "applied": self.coupon_applied,
                "applied_amount": (
                    None
                    if not self.coupon_applied
                    else str(self.coupon.applied_amount() or Decimal("0"))
                ),
            },
            "history": {
                "observation_count": self.observation_count,
                "prior_observation_count": self.prior_observation_count,
                "source": self.history_source,
                "window_days": self.history_window_days,
            },
            "components": [component.to_contract() for component in self.components],
            "warnings": [warning.to_contract() for warning in self.warnings],
        }


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _round_percent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _percent_above(price: Decimal, reference: Decimal) -> Decimal:
    return (price - reference) / reference * Decimal(100)


def _score_historical_position(percent_above: Decimal) -> int:
    """Map the position above the observed minimum to the approved score."""

    if percent_above <= 5:
        return 100
    if percent_above <= 10:
        return 90
    if percent_above <= 20:
        return 75
    if percent_above <= 30:
        return 55
    if percent_above <= 40:
        return 35
    return 10


def _score_recent_drop(drop_percent: Decimal) -> int:
    """Map the recent drop percentage to the approved score."""

    if drop_percent >= 25:
        return 100
    if drop_percent >= 20:
        return 90
    if drop_percent >= 15:
        return 80
    if drop_percent >= 10:
        return 65
    if drop_percent >= 5:
        return 45
    return 20


def _score_marketplace_comparison(percent_above: Decimal) -> int:
    """Map the position above the best known price to the approved score."""

    if percent_above <= 0:
        return 100
    if percent_above <= 3:
        return 90
    if percent_above <= 7:
        return 75
    if percent_above <= 12:
        return 55
    if percent_above <= 20:
        return 30
    return 10


def _select_history_window(
    prior: Sequence[PriceHistoryFact], as_of: datetime
) -> tuple[Sequence[PriceHistoryFact], str, int | None]:
    """Select the reference window following ``30d > lifetime > 7d``.

    The 30-day window is preferred; when the product has no observation in that
    window the lifetime window is used. The 7-day fallback is a strict subset of
    both, so it only matters if a future calibration narrows the preference.
    """

    cutoff = as_of - timedelta(days=PREFERRED_HISTORY_WINDOW_DAYS)
    window = [fact for fact in prior if _to_utc(fact.observed_at) >= cutoff]
    if window:
        return window, "30d", PREFERRED_HISTORY_WINDOW_DAYS
    # Lifetime is the next priority; the 7-day window is a strict subset of both
    # 30d and lifetime, so it never carries evidence they lack.
    return list(prior), "lifetime", None


def compute_price_opportunity(
    *,
    candidate_id: str,
    current_price: Decimal,
    as_of: datetime,
    original_price: Decimal | None = None,
    shipping_cost: Decimal | None = None,
    coupon: Coupon | None = None,
    history: Sequence[PriceHistoryFact] = (),
    comparable: ComparableEvidence | None = None,
) -> PriceOpportunityResult:
    """Compute the deterministic Price Opportunity breakdown.

    ``as_of`` is the instant of the Candidate's current offer; observations at
    or after it are the current condition and never a history reference. The
    function never mutates its inputs and is reproducible for the same facts.
    """

    resolved_coupon = coupon or Coupon()
    reference_time = _to_utc(as_of)
    # Non-positive observations are invalid data and never become a reference.
    available = [
        fact for fact in history if fact.price > 0 and _to_utc(fact.observed_at) <= reference_time
    ]
    ordered = sorted(
        (fact for fact in available if _to_utc(fact.observed_at) < reference_time),
        key=lambda fact: _to_utc(fact.observed_at),
    )
    observation_count = len(available)
    prior_observation_count = len(ordered)

    warnings: list[PriceOpportunityWarning] = []

    # --- Historical Position (45%) -----------------------------------------
    if not ordered:
        historical_score: int | None = NEUTRAL_SCORE
        history_source = "none"
        history_window_days: int | None = None
        historical_detail: dict[str, Any] = {"reason": "insufficient_history"}
        warnings.append(
            PriceOpportunityWarning(
                code=WARNING_SHORT_PRICE_HISTORY,
                message=(
                    "Histórico insuficiente para posição histórica; valor neutro 50 "
                    "e penalidade de Confidence"
                ),
                context={"prior_observation_count": 0},
            )
        )
    else:
        window, history_source, history_window_days = _select_history_window(
            ordered, reference_time
        )
        minimum = min(fact.price for fact in window)
        percent_above = _round_percent(_percent_above(current_price, minimum))
        if current_price <= minimum:
            historical_score = 100
            historical_detail = {
                "minimum": str(minimum),
                "percent_above_minimum": "0.0000",
                "new_minimum": True,
            }
        else:
            historical_score = _score_historical_position(percent_above)
            historical_detail = {
                "minimum": str(minimum),
                "percent_above_minimum": str(percent_above),
                "new_minimum": False,
            }

    # --- Recent Price Drop (20%) -------------------------------------------
    if not ordered:
        drop_score: int | None = NEUTRAL_SCORE
        drop_detail: dict[str, Any] = {"reason": "no_reference"}
        warnings.append(
            PriceOpportunityWarning(
                code=WARNING_NO_PRICE_REFERENCE,
                message="Sem referência de preço anterior; queda recente usa neutro 50",
                context={},
            )
        )
    else:
        reference = ordered[-1]
        drop_percent = _round_percent(
            (reference.price - current_price) / reference.price * Decimal(100)
        )
        drop_score = _score_recent_drop(drop_percent)
        drop_detail = {
            "reference_price": str(reference.price),
            "reference_observed_at": _to_utc(reference.observed_at).isoformat(),
            "drop_percent": str(drop_percent),
        }

    # --- Effective price (only reliable when shipping is known) -------------
    shipping_known = shipping_cost is not None
    applied_coupon = resolved_coupon.applied_amount()
    if shipping_known:
        assert shipping_cost is not None
        effective_price: Decimal | None = current_price + shipping_cost - (applied_coupon or 0)
    else:
        effective_price = None

    if not shipping_known:
        warnings.append(
            PriceOpportunityWarning(
                code=WARNING_UNKNOWN_SHIPPING,
                message=(
                    "Frete desconhecido; preço efetivo e impacto de frete não são "
                    "considerados confiáveis"
                ),
                context={},
            )
        )

    if not resolved_coupon.is_confirmed and resolved_coupon.amount is not None:
        warnings.append(
            PriceOpportunityWarning(
                code=WARNING_COUPON_NOT_CONFIRMED,
                message=(
                    "Cupom não confirmado não reduz integralmente o preço efetivo nem vira claim"
                ),
                context={"coupon_state": resolved_coupon.state.value},
            )
        )

    if original_price is not None:
        warnings.append(
            PriceOpportunityWarning(
                code=WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF,
                message=(
                    "Preço riscado do marketplace não é prova de vantagem e não é "
                    "usado como referência"
                ),
                context={"original_price": str(original_price)},
            )
        )

    # --- Marketplace Comparison (20%) --------------------------------------
    if comparable is None or effective_price is None or comparable.price <= 0:
        comparison_score: int | None = NEUTRAL_SCORE
        if comparable is None:
            reason = "no_reference"
        elif comparable.price <= 0:
            reason = "invalid_reference"
        else:
            reason = "unknown_shipping"
        comparison_detail: dict[str, Any] = {"reason": reason}
        warnings.append(
            PriceOpportunityWarning(
                code=WARNING_NO_MARKETPLACE_REFERENCE,
                message=(
                    "Sem referência comparável confiável; comparação de marketplace usa neutro 50"
                ),
                context={},
            )
        )
    else:
        percent_above = _round_percent(_percent_above(effective_price, comparable.price))
        comparison_score = _score_marketplace_comparison(percent_above)
        comparison_detail = {
            "comparable_price": str(comparable.price),
            "comparable_marketplace": comparable.marketplace,
            "percent_above": str(percent_above),
        }

    # --- Coupon / Final Price (10%) and Shipping Impact (5%) ----------------
    # The SDD freezes the weights but does not approve score ranges for these
    # two components, so they stay explicit calibration gaps (no invented value).
    coupon_component = PriceOpportunityComponent(
        name=PriceOpportunityComponentName.COUPON_FINAL_PRICE,
        weight=WEIGHT_COUPON_FINAL_PRICE,
        score=None,
        calibrated=False,
        detail={
            "state": resolved_coupon.state.value,
            "amount": None if resolved_coupon.amount is None else str(resolved_coupon.amount),
            "applied": applied_coupon is not None,
            "reason": "calibration_required",
        },
    )
    shipping_component = PriceOpportunityComponent(
        name=PriceOpportunityComponentName.SHIPPING_IMPACT,
        weight=WEIGHT_SHIPPING_IMPACT,
        score=None,
        calibrated=False,
        detail={
            "shipping_cost": None if shipping_cost is None else str(shipping_cost),
            "known": shipping_known,
            "reason": "calibration_required",
        },
    )
    warnings.append(
        PriceOpportunityWarning(
            code=WARNING_CALIBRATION_REQUIRED,
            message=(
                "Faixas de Coupon/Final Price e Shipping Impact não calibradas no "
                "SDD; componentes reportados como lacuna, sem valor inventado"
            ),
            context={
                "components": [
                    PriceOpportunityComponentName.COUPON_FINAL_PRICE.value,
                    PriceOpportunityComponentName.SHIPPING_IMPACT.value,
                ]
            },
        )
    )

    components = (
        PriceOpportunityComponent(
            name=PriceOpportunityComponentName.HISTORICAL_POSITION,
            weight=WEIGHT_HISTORICAL_POSITION,
            score=historical_score,
            calibrated=True,
            detail=historical_detail,
        ),
        PriceOpportunityComponent(
            name=PriceOpportunityComponentName.RECENT_PRICE_DROP,
            weight=WEIGHT_RECENT_PRICE_DROP,
            score=drop_score,
            calibrated=True,
            detail=drop_detail,
        ),
        PriceOpportunityComponent(
            name=PriceOpportunityComponentName.MARKETPLACE_COMPARISON,
            weight=WEIGHT_MARKETPLACE_COMPARISON,
            score=comparison_score,
            calibrated=True,
            detail=comparison_detail,
        ),
        coupon_component,
        shipping_component,
    )

    calibrated_components = [component for component in components if component.calibrated]
    weight_covered = sum(component.weight for component in calibrated_components)
    if calibrated_components and weight_covered > 0:
        weighted = sum(
            Decimal(component.score or 0) * component.weight for component in calibrated_components
        )
        price_opportunity: int | None = int(
            (weighted / Decimal(weight_covered)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    else:
        price_opportunity = None

    return PriceOpportunityResult(
        candidate_id=candidate_id,
        price_opportunity=price_opportunity,
        fully_calibrated=all(component.calibrated for component in components),
        weight_covered=weight_covered,
        effective_price=effective_price,
        current_price=current_price,
        original_price=original_price,
        shipping_cost=shipping_cost,
        shipping_known=shipping_known,
        coupon=resolved_coupon,
        coupon_applied=applied_coupon is not None,
        observation_count=observation_count,
        prior_observation_count=prior_observation_count,
        history_source=history_source,
        history_window_days=history_window_days,
        components=components,
        warnings=tuple(warnings),
        as_of=reference_time,
    )


__all__ = [
    "NEUTRAL_SCORE",
    "PRICE_OPPORTUNITY_INPUT_INVALID",
    "PRICE_OPPORTUNITY_SCHEMA_VERSION",
    "PRICE_OPPORTUNITY_SCORING_VERSION",
    "WARNING_CALIBRATION_REQUIRED",
    "WARNING_COUPON_NOT_CONFIRMED",
    "WARNING_NO_MARKETPLACE_REFERENCE",
    "WARNING_NO_PRICE_REFERENCE",
    "WARNING_SHORT_PRICE_HISTORY",
    "WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF",
    "WARNING_UNKNOWN_SHIPPING",
    "WEIGHT_COUPON_FINAL_PRICE",
    "WEIGHT_HISTORICAL_POSITION",
    "WEIGHT_MARKETPLACE_COMPARISON",
    "WEIGHT_RECENT_PRICE_DROP",
    "WEIGHT_SHIPPING_IMPACT",
    "ComparableEvidence",
    "Coupon",
    "CouponState",
    "PriceHistoryFact",
    "PriceOpportunityComponent",
    "PriceOpportunityComponentName",
    "PriceOpportunityError",
    "PriceOpportunityResult",
    "PriceOpportunityWarning",
    "compute_price_opportunity",
    "price_opportunity_input_invalid_error",
]
