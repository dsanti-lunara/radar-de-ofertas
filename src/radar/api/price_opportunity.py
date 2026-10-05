"""Candidate Price Opportunity public endpoint (RDR-023).

``GET /candidates/{candidate_id}/price-opportunity`` evaluates the deterministic
Price Opportunity breakdown from the Candidate's persisted Offer and
append-only price history. The endpoint is read-only and idempotent: repeated
calls with the same facts and conditions yield the same result and no commercial
side effect is triggered.

Confirmed conditions that the manual capture does not persist yet (coupon,
shipping, comparable evidence) can be supplied as optional query parameters.
They are validated here and never trusted blindly; when absent the persisted
value is used and an absent value stays an explicit gap. Structured errors reuse
the shared ``RadarException`` handler registered by the capture boundary.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER
from radar.application.correlation import bind_correlation_id
from radar.application.price_opportunity_service import PriceOpportunityService
from radar.domain.capture import CaptureValidationError, parse_money, sanitize_single_line
from radar.domain.price_opportunity import (
    ComparableEvidence,
    Coupon,
    CouponState,
    price_opportunity_input_invalid_error,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository


def _parse_optional_money(value: str | None, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return parse_money(value, field_name=field_name)
    except CaptureValidationError as exc:
        raise price_opportunity_input_invalid_error(
            exc.error.message, context={"field": field_name}
        ) from exc


def _parse_coupon(state: str | None, amount: str | None, code: str | None) -> Coupon | None:
    if state is None and amount is None and code is None:
        return None
    if state is None:
        raise price_opportunity_input_invalid_error(
            "coupon_state é obrigatório quando cupom é informado",
            context={"field": "coupon_state"},
        )
    try:
        coupon_state = CouponState(state)
    except ValueError as exc:
        raise price_opportunity_input_invalid_error(
            "coupon_state inválido",
            context={"field": "coupon_state", "allowed": [item.value for item in CouponState]},
        ) from exc
    return Coupon(
        state=coupon_state,
        amount=_parse_optional_money(amount, field_name="coupon_amount"),
        code=None if code is None else sanitize_single_line(code) or None,
    )


def _parse_comparable(price: str | None, marketplace: str | None) -> ComparableEvidence | None:
    if price is None and marketplace is None:
        return None
    if price is None:
        raise price_opportunity_input_invalid_error(
            "comparable_price é obrigatório quando evidência comparável é informada",
            context={"field": "comparable_price"},
        )
    parsed_price = _parse_optional_money(price, field_name="comparable_price")
    if parsed_price is None or parsed_price <= 0:
        raise price_opportunity_input_invalid_error(
            "comparable_price deve ser maior que zero",
            context={"field": "comparable_price"},
        )
    return ComparableEvidence(
        price=parsed_price,
        marketplace=None if marketplace is None else sanitize_single_line(marketplace) or None,
    )


def build_price_opportunity_router(engine: Engine) -> APIRouter:
    """Build the Price Opportunity router wired to the SQLite repository."""

    router = APIRouter(tags=["price-opportunity"])
    service = PriceOpportunityService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
    )

    @router.get("/candidates/{candidate_id}/price-opportunity")
    def evaluate_price_opportunity(
        candidate_id: str,
        request: Request,
        shipping_cost: str | None = None,
        coupon_state: str | None = None,
        coupon_amount: str | None = None,
        coupon_code: str | None = None,
        comparable_price: str | None = None,
        comparable_marketplace: str | None = None,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        coupon = _parse_coupon(coupon_state, coupon_amount, coupon_code)
        comparable = _parse_comparable(comparable_price, comparable_marketplace)
        parsed_shipping = _parse_optional_money(shipping_cost, field_name="shipping_cost")
        result = service.evaluate(
            candidate_id,
            shipping_cost=parsed_shipping,
            coupon=coupon,
            comparable=comparable,
        )
        return JSONResponse(
            status_code=200,
            content={**result.to_contract(), "correlation_id": correlation_id},
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_price_opportunity_router",
]
