"""Candidate Allowed Claims public endpoint (RDR-032).

``GET /candidates/{candidate_id}/allowed-claims`` returns the versioned claims
the backend sustains with evidence for one Evaluation version, so editorial
content can only use claims produced by the backend (AUT-063, AUT-076). The
endpoint is read-only and idempotent: repeated calls with the same Evaluation and
evidence yield the same claims and no commercial side effect is triggered.

The Evaluation is resolved from the immutable store (the latest one, or the
``evaluation_id`` supplied); a Candidate without an Evaluation fails closed
because claims are always bound to an Evaluation version. A confirmed coupon that
the manual capture does not persist yet can be supplied as an optional query
parameter, validated here and never trusted blindly. Structured errors reuse the
shared ``RadarException`` handler registered by the capture boundary.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER
from radar.application.allowed_claims_service import AllowedClaimsService
from radar.application.correlation import bind_correlation_id
from radar.domain.allowed_claims import ALLOWED_CLAIMS_SCHEMA_VERSION
from radar.domain.allowed_claims import (
    allowed_claims_input_invalid_error as _input_invalid,
)
from radar.domain.capture import CaptureValidationError, parse_money, sanitize_single_line
from radar.domain.price_opportunity import Coupon, CouponState
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository


def _parse_optional_money(value: str | None, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return parse_money(value, field_name=field_name)
    except CaptureValidationError as exc:
        raise _input_invalid(exc.error.message, context={"field": field_name}) from exc


def _parse_coupon(state: str | None, amount: str | None, code: str | None) -> Coupon | None:
    if state is None and amount is None and code is None:
        return None
    if state is None:
        raise _input_invalid(
            "coupon_state é obrigatório quando cupom é informado",
            context={"field": "coupon_state"},
        )
    try:
        coupon_state = CouponState(state)
    except ValueError as exc:
        raise _input_invalid(
            "coupon_state inválido",
            context={"field": "coupon_state", "allowed": [item.value for item in CouponState]},
        ) from exc
    return Coupon(
        state=coupon_state,
        amount=_parse_optional_money(amount, field_name="coupon_amount"),
        code=None if code is None else sanitize_single_line(code) or None,
    )


def build_allowed_claims_router(engine: Engine) -> APIRouter:
    """Build the Allowed Claims router wired to the SQLite stores."""

    router = APIRouter(tags=["allowed-claims"])
    service = AllowedClaimsService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        evaluations=SqlAlchemyEvaluationRepository(engine=engine),
    )

    @router.get("/candidates/{candidate_id}/allowed-claims")
    def list_allowed_claims(
        candidate_id: str,
        request: Request,
        evaluation_id: str | None = None,
        coupon_state: str | None = None,
        coupon_amount: str | None = None,
        coupon_code: str | None = None,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        coupon = _parse_coupon(coupon_state, coupon_amount, coupon_code)
        result = service.get(candidate_id, evaluation_id=evaluation_id, coupon=coupon)
        return JSONResponse(
            status_code=200,
            content={
                **result.to_contract(),
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "ALLOWED_CLAIMS_SCHEMA_VERSION",
    "build_allowed_claims_router",
]
