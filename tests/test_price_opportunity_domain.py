from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from radar.domain.price_opportunity import (
    NEUTRAL_SCORE,
    WARNING_CALIBRATION_REQUIRED,
    WARNING_COUPON_NOT_CONFIRMED,
    WARNING_NO_MARKETPLACE_REFERENCE,
    WARNING_NO_PRICE_REFERENCE,
    WARNING_SHORT_PRICE_HISTORY,
    WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF,
    WARNING_UNKNOWN_SHIPPING,
    WEIGHT_COUPON_FINAL_PRICE,
    WEIGHT_HISTORICAL_POSITION,
    WEIGHT_MARKETPLACE_COMPARISON,
    WEIGHT_RECENT_PRICE_DROP,
    WEIGHT_SHIPPING_IMPACT,
    ComparableEvidence,
    Coupon,
    CouponState,
    PriceHistoryFact,
    PriceOpportunityComponentName,
    compute_price_opportunity,
)

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
PRIOR_AT = AS_OF - timedelta(days=1)


def _history(*prices: str, observed_at: datetime = PRIOR_AT) -> tuple[PriceHistoryFact, ...]:
    return tuple(
        PriceHistoryFact(price=Decimal(price), observed_at=observed_at + timedelta(minutes=index))
        for index, price in enumerate(prices)
    )


def _result(
    current: str,
    *,
    history: tuple[PriceHistoryFact, ...] = (),
    shipping: str | None = None,
    coupon: Coupon | None = None,
    comparable: ComparableEvidence | None = None,
    original: str | None = None,
):
    return compute_price_opportunity(
        candidate_id="cand_1",
        current_price=Decimal(current),
        as_of=AS_OF,
        original_price=None if original is None else Decimal(original),
        shipping_cost=None if shipping is None else Decimal(shipping),
        coupon=coupon,
        history=history,
        comparable=comparable,
    )


def _score(result, name: PriceOpportunityComponentName) -> int | None:
    return result.component(name).score


# --- Weights and ranges (acceptance criterion 1) ---------------------------


def test_component_weights_follow_sdd() -> None:
    result = _result("100.00")
    weights = {component.name: component.weight for component in result.components}
    assert weights == {
        PriceOpportunityComponentName.HISTORICAL_POSITION: 45,
        PriceOpportunityComponentName.RECENT_PRICE_DROP: 20,
        PriceOpportunityComponentName.MARKETPLACE_COMPARISON: 20,
        PriceOpportunityComponentName.COUPON_FINAL_PRICE: 10,
        PriceOpportunityComponentName.SHIPPING_IMPACT: 5,
    }
    assert WEIGHT_HISTORICAL_POSITION == 45
    assert WEIGHT_RECENT_PRICE_DROP == 20
    assert WEIGHT_MARKETPLACE_COMPARISON == 20
    assert WEIGHT_COUPON_FINAL_PRICE == 10
    assert WEIGHT_SHIPPING_IMPACT == 5


@pytest.mark.parametrize(
    ("minimum", "current", "expected"),
    [
        ("100.00", "95.00", 100),  # new minimum observed
        ("100.00", "105.00", 100),  # <=5%
        ("100.00", "110.00", 90),  # <=10%
        ("100.00", "120.00", 75),  # <=20%
        ("100.00", "130.00", 55),  # <=30%
        ("100.00", "140.00", 35),  # <=40%
        ("100.00", "141.00", 10),  # >40%
    ],
)
def test_historical_position_ranges_follow_sdd(minimum: str, current: str, expected: int) -> None:
    result = _result(current, history=_history(minimum))
    assert _score(result, PriceOpportunityComponentName.HISTORICAL_POSITION) == expected


@pytest.mark.parametrize(
    ("reference", "current", "expected"),
    [
        ("100.00", "75.00", 100),  # >=25%
        ("100.00", "80.00", 90),  # 20-24.99%
        ("100.00", "85.00", 80),  # 15-19.99%
        ("100.00", "90.00", 65),  # 10-14.99%
        ("100.00", "95.00", 45),  # 5-9.99%
        ("100.00", "96.00", 20),  # <5%
        ("100.00", "100.00", 20),  # no drop
    ],
)
def test_recent_price_drop_ranges_follow_sdd(reference: str, current: str, expected: int) -> None:
    result = _result(current, history=_history(reference))
    assert _score(result, PriceOpportunityComponentName.RECENT_PRICE_DROP) == expected


@pytest.mark.parametrize(
    ("comparable", "current", "expected"),
    [
        ("100.00", "100.00", 100),  # best known price
        ("100.00", "103.00", 90),  # <=3%
        ("100.00", "107.00", 75),  # <=7%
        ("100.00", "112.00", 55),  # <=12%
        ("100.00", "120.00", 30),  # <=20%
        ("100.00", "121.00", 10),  # >20%
    ],
)
def test_marketplace_comparison_ranges_follow_sdd(
    comparable: str, current: str, expected: int
) -> None:
    result = _result(
        current,
        shipping="0.00",
        comparable=ComparableEvidence(price=Decimal(comparable), marketplace="SHOPEE"),
    )
    assert _score(result, PriceOpportunityComponentName.MARKETPLACE_COMPARISON) == expected


# --- Insufficient history uses neutral 50 + Confidence warning (criterion 2) -


def test_insufficient_history_uses_neutral_and_warns() -> None:
    result = _result("79.90")

    assert _score(result, PriceOpportunityComponentName.HISTORICAL_POSITION) == NEUTRAL_SCORE
    assert _score(result, PriceOpportunityComponentName.RECENT_PRICE_DROP) == NEUTRAL_SCORE
    assert result.prior_observation_count == 0
    assert result.history_source == "none"
    codes = [warning.code for warning in result.warnings]
    assert WARNING_SHORT_PRICE_HISTORY in codes
    assert WARNING_NO_PRICE_REFERENCE in codes


def test_insufficient_history_does_not_become_zero() -> None:
    result = _result("79.90")
    assert result.price_opportunity == NEUTRAL_SCORE
    assert result.price_opportunity != 0


# --- Coupon states (acceptance criterion 3) ---------------------------------


def test_unconfirmed_coupon_does_not_reduce_effective_price() -> None:
    result = _result(
        "100.00",
        shipping="0.00",
        coupon=Coupon(state=CouponState.LIKELY, amount=Decimal("20.00"), code="TALVEZ"),
    )
    assert result.effective_price == Decimal("100.00")
    assert result.coupon_applied is False
    assert WARNING_COUPON_NOT_CONFIRMED in [warning.code for warning in result.warnings]


def test_confirmed_coupon_reduces_effective_price() -> None:
    result = _result(
        "100.00",
        shipping="5.00",
        coupon=Coupon(state=CouponState.CONFIRMED, amount=Decimal("20.00"), code="OK"),
    )
    assert result.effective_price == Decimal("85.00")
    assert result.coupon_applied is True
    assert WARNING_COUPON_NOT_CONFIRMED not in [warning.code for warning in result.warnings]


@pytest.mark.parametrize("state", [CouponState.UNKNOWN, CouponState.NOT_APPLICABLE])
def test_other_coupon_states_never_reduce_effective_price(state: CouponState) -> None:
    result = _result(
        "100.00",
        shipping="0.00",
        coupon=Coupon(state=state, amount=Decimal("20.00")),
    )
    assert result.effective_price == Decimal("100.00")
    assert result.coupon_applied is False


def test_coupon_and_shipping_components_are_explicit_calibration_gaps() -> None:
    result = _result("100.00", shipping="5.00", coupon=Coupon(state=CouponState.CONFIRMED))
    coupon_component = result.component(PriceOpportunityComponentName.COUPON_FINAL_PRICE)
    shipping_component = result.component(PriceOpportunityComponentName.SHIPPING_IMPACT)
    assert coupon_component.score is None
    assert coupon_component.calibrated is False
    assert shipping_component.score is None
    assert shipping_component.calibrated is False
    assert result.fully_calibrated is False
    assert result.weight_covered == 85
    assert WARNING_CALIBRATION_REQUIRED in [warning.code for warning in result.warnings]


# --- Unknown shipping and insufficient reference (acceptance criterion 4) ----


def test_unknown_shipping_is_explicit() -> None:
    result = _result("100.00")
    assert result.shipping_known is False
    assert result.effective_price is None
    assert WARNING_UNKNOWN_SHIPPING in [warning.code for warning in result.warnings]


def test_unknown_shipping_disables_marketplace_comparison() -> None:
    result = _result("100.00", comparable=ComparableEvidence(price=Decimal("80.00")))
    assert _score(result, PriceOpportunityComponentName.MARKETPLACE_COMPARISON) == NEUTRAL_SCORE
    assert WARNING_NO_MARKETPLACE_REFERENCE in [warning.code for warning in result.warnings]


def test_absent_comparison_reference_is_explicit_and_neutral() -> None:
    result = _result("100.00", shipping="0.00")
    assert _score(result, PriceOpportunityComponentName.MARKETPLACE_COMPARISON) == NEUTRAL_SCORE
    assert WARNING_NO_MARKETPLACE_REFERENCE in [warning.code for warning in result.warnings]


def test_struck_through_price_is_not_proof_of_advantage() -> None:
    with_original = _result("100.00", original="250.00")
    without_original = _result("100.00")

    assert WARNING_STRUCK_THROUGH_PRICE_NOT_PROOF in [
        warning.code for warning in with_original.warnings
    ]
    # The struck-through price changes neither the components nor the score.
    assert _score(with_original, PriceOpportunityComponentName.HISTORICAL_POSITION) == NEUTRAL_SCORE
    assert _score(with_original, PriceOpportunityComponentName.RECENT_PRICE_DROP) == NEUTRAL_SCORE
    assert with_original.price_opportunity == without_original.price_opportunity


def test_struck_through_price_is_not_used_as_history_reference() -> None:
    # Only real observations are references: a huge original_price does not
    # fabricate a 60% drop.
    result = _result("100.00", history=_history("100.00"), original="250.00")
    assert _score(result, PriceOpportunityComponentName.RECENT_PRICE_DROP) == 20


# --- Aggregation and determinism -------------------------------------------


def test_partial_score_uses_approved_weights_only() -> None:
    result = _result(
        "70.00",
        history=_history("100.00"),
        shipping="0.00",
        comparable=ComparableEvidence(price=Decimal("70.00")),
    )
    assert _score(result, PriceOpportunityComponentName.HISTORICAL_POSITION) == 100
    assert _score(result, PriceOpportunityComponentName.RECENT_PRICE_DROP) == 100
    assert _score(result, PriceOpportunityComponentName.MARKETPLACE_COMPARISON) == 100
    assert result.price_opportunity == 100
    assert result.weight_covered == 85
    assert result.fully_calibrated is False


def test_calculation_is_deterministic() -> None:
    first = _result("90.00", history=_history("100.00"), shipping="5.00")
    second = _result("90.00", history=_history("100.00"), shipping="5.00")
    assert first.to_contract() == second.to_contract()


def test_contract_serializes_money_and_utc() -> None:
    result = _result("90.00", history=_history("100.00"), shipping="5.00")
    contract = result.to_contract()
    assert contract["schema_version"] == "1.0"
    assert contract["status"] == "EVALUATED"
    assert contract["candidate_id"] == "cand_1"
    assert contract["current_price"] == "90.00"
    assert contract["effective_price"] == "95.00"
    assert contract["as_of"] == "2026-10-05T12:00:00+00:00"
    assert contract["scoring_version"] == "price-opportunity-1.0"
    assert len(contract["components"]) == 5
