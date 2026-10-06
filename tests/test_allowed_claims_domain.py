from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from radar.domain.allowed_claims import (
    ALLOWED_CLAIMS_ENGINE_VERSION,
    ALLOWED_CLAIMS_SCHEMA_VERSION,
    FORBIDDEN_CLAIMS,
    ClaimEvidenceType,
    ClaimOfferFacts,
    ClaimPriceFact,
    ClaimType,
    ClaimUnit,
    compute_allowed_claims,
)
from radar.domain.price_opportunity import Coupon, CouponState

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _offer(
    *,
    price: str = "80",
    sales_count: int | None = 150,
    coupon: Coupon | None = None,
    original_price: str | None = None,
) -> ClaimOfferFacts:
    return ClaimOfferFacts(
        offer_id="off_1",
        current_price=Decimal(price),
        observed_at=AS_OF,
        source="BROWSER_EXTENSION",
        correlation_id="cid-offer",
        raw_capture_id="raw_offer",
        sales_count=sales_count,
        coupon=coupon,
        original_price=None if original_price is None else Decimal(original_price),
    )


def _fact(observation_id: str, price: str, days_ago: int) -> ClaimPriceFact:
    return ClaimPriceFact(
        observation_id=observation_id,
        price=Decimal(price),
        observed_at=AS_OF - timedelta(days=days_ago),
        source="BROWSER_EXTENSION",
        correlation_id=f"cid-{observation_id}",
        raw_capture_id=f"raw-{observation_id}",
    )


def _compute(*, offer: ClaimOfferFacts | None = None, history: list[ClaimPriceFact] | None = None):
    return compute_allowed_claims(
        candidate_id="cand_1",
        evaluation_id="eval_1",
        evaluation_decision="APPROVE",
        offer=offer or _offer(),
        history=history or [],
    )


def _claim(result, claim_type: ClaimType):
    claim = result.claim(claim_type)
    assert claim is not None, claim_type
    return claim


def test_current_price_and_history_claims_carry_traceable_evidence() -> None:
    result = _compute(history=[_fact("obs_old", "100", 10)])

    current = _claim(result, ClaimType.CURRENT_PRICE)
    assert current.value == "80"
    assert current.unit is ClaimUnit.MONEY
    assert current.evidence[0].evidence_type is ClaimEvidenceType.OFFER
    assert current.evidence[0].reference_id == "off_1"
    assert current.evidence[0].raw_capture_id == "raw_offer"
    assert current.evidence[0].field == "current_price"

    previous = _claim(result, ClaimType.PREVIOUS_OBSERVED_PRICE)
    assert previous.value == "100"
    assert previous.evidence[0].evidence_type is ClaimEvidenceType.PRICE_OBSERVATION
    assert previous.evidence[0].reference_id == "obs_old"
    assert previous.evidence[0].raw_capture_id == "raw-obs_old"

    drop = _claim(result, ClaimType.PRICE_DROP_PERCENT)
    assert drop.value == "20.00"
    assert drop.unit is ClaimUnit.PERCENT
    assert {item.reference_id for item in drop.evidence} == {"off_1", "obs_old"}


def test_no_history_omits_previous_drop_and_lowest() -> None:
    result = _compute(history=[])

    assert result.claim(ClaimType.PREVIOUS_OBSERVED_PRICE) is None
    assert result.claim(ClaimType.PRICE_DROP_PERCENT) is None
    assert result.claim(ClaimType.LOWEST_OBSERVED_30D) is None
    omitted = {item.claim_type: item.reason_code for item in result.omitted_claims}
    assert omitted[ClaimType.PREVIOUS_OBSERVED_PRICE] == "NO_PRIOR_OBSERVATION"
    assert omitted[ClaimType.LOWEST_OBSERVED_30D] == "HISTORY_INSUFFICIENT"
    assert any(warning.code == "NO_PRICE_HISTORY" for warning in result.warnings)


def test_lowest_observed_30d_requires_a_covered_window() -> None:
    # Only a recent observation: the series does not cover the 30-day window, so
    # a "lowest observed in 30 days" claim would be false and must be omitted.
    recent = _compute(history=[_fact("obs_recent", "60", 2)])
    assert recent.claim(ClaimType.LOWEST_OBSERVED_30D) is None
    assert any(
        warning.code == "LOWEST_OBSERVED_30D_HISTORY_INSUFFICIENT" for warning in recent.warnings
    )

    # An observation before the window start plus one inside it brackets the
    # window; the minimum is then a genuine 30-day minimum.
    covered = _compute(history=[_fact("obs_old", "100", 40), _fact("obs_mid", "70", 10)])
    lowest = _claim(covered, ClaimType.LOWEST_OBSERVED_30D)
    assert lowest.value == "70"
    assert any(item.reference_id == "obs_mid" for item in lowest.evidence)
    assert any(item.field == "coverage" for item in lowest.evidence)


def test_unconfirmed_coupon_is_not_proof_and_confirmed_coupon_is() -> None:
    likely = _compute(offer=_offer(coupon=Coupon(state=CouponState.LIKELY, amount=Decimal("10"))))
    assert likely.claim(ClaimType.CONFIRMED_COUPON) is None
    omitted = {item.claim_type: item.reason_code for item in likely.omitted_claims}
    assert omitted[ClaimType.CONFIRMED_COUPON] == "COUPON_NOT_CONFIRMED"
    assert any(warning.code == "COUPON_NOT_CONFIRMED" for warning in likely.warnings)

    unknown = _compute(offer=_offer(coupon=Coupon(state=CouponState.UNKNOWN)))
    assert unknown.claim(ClaimType.CONFIRMED_COUPON) is None

    confirmed = _compute(
        offer=_offer(
            coupon=Coupon(state=CouponState.CONFIRMED, amount=Decimal("10"), code="RADAR10")
        )
    )
    coupon_claim = _claim(confirmed, ClaimType.CONFIRMED_COUPON)
    assert coupon_claim.value == "RADAR10"
    assert coupon_claim.unit is ClaimUnit.COUPON


def test_struck_through_price_is_never_proof() -> None:
    result = _compute(offer=_offer(original_price="199"), history=[])

    # The struck-through price does not create a history reference or a claim.
    assert result.claim(ClaimType.PREVIOUS_OBSERVED_PRICE) is None
    assert result.claim(ClaimType.PRICE_DROP_PERCENT) is None
    assert result.claim(ClaimType.LOWEST_OBSERVED_30D) is None
    assert any(warning.code == "STRUCK_THROUGH_PRICE_NOT_PROOF" for warning in result.warnings)


def test_unsupported_claims_are_omitted_and_forbidden_claims_are_explicit() -> None:
    result = _compute(offer=_offer(sales_count=None), history=[])

    assert result.claim(ClaimType.SALES_COUNT) is None
    omitted = {item.claim_type: item.reason_code for item in result.omitted_claims}
    assert omitted[ClaimType.SALES_COUNT] == "DATA_UNAVAILABLE"
    # The backend never emits a forbidden claim and the AI cannot create one.
    produced = {claim.claim_type.value for claim in result.claims}
    assert produced.isdisjoint(FORBIDDEN_CLAIMS)
    contract = result.to_contract()
    assert contract["forbidden_claims"] == list(FORBIDDEN_CLAIMS)
    assert contract["engine_version"] == ALLOWED_CLAIMS_ENGINE_VERSION
    assert contract["schema_version"] == ALLOWED_CLAIMS_SCHEMA_VERSION


def test_sales_count_claim_uses_persisted_offer_evidence() -> None:
    result = _compute(offer=_offer(sales_count=2300))
    claim = _claim(result, ClaimType.SALES_COUNT)
    assert claim.value == "2300"
    assert claim.unit is ClaimUnit.COUNT
    assert claim.evidence[0].field == "sales_count"


def test_engine_is_deterministic_for_the_same_facts() -> None:
    history = [_fact("obs_old", "100", 40), _fact("obs_mid", "70", 10)]
    first = _compute(history=history).to_contract()
    second = _compute(history=history).to_contract()
    assert first == second
