"""Candidate Purchase Source public endpoints (RDR-031).

``POST /candidates/{candidate_id}/purchase-source`` compares the Candidate's
affiliate source with the supplied reliable alternatives and persists an
append-only decision with its Evidence. ``GET /candidates/{candidate_id}/
purchase-source`` returns the stored decisions oldest first, so the guardrail is
observable and auditable from the public boundary.

Only reliable and comparable sources are compared: product equivalence must be
positively identified, conditions must match and the effective price requires
known shipping and a ``CONFIRMED`` coupon. Commission is never an input, so the
decision can never favour a materially worse affiliate option. No AI, affiliate
link or publication is triggered here. Structured errors reuse the shared
``RadarException`` handler registered by the capture boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import (
    CORRELATION_HEADER,
    PurchaseSourceAlternativeContract,
    PurchaseSourceRequestContract,
)
from radar.application.correlation import bind_correlation_id
from radar.application.purchase_source_service import PurchaseSourceService
from radar.domain.capture import (
    CaptureValidationError,
    parse_money,
    sanitize_single_line,
    validate_source_url,
)
from radar.domain.price_opportunity import Coupon, CouponState
from radar.domain.purchase_source import (
    PURCHASE_SOURCE_SCHEMA_VERSION,
    PurchaseSource,
    PurchaseSourcePolicy,
    purchase_source_input_invalid_error,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.purchase_source_repository import (
    SqlAlchemyPurchaseSourceDecisionRepository,
)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return sanitize_single_line(value) or None


def _money(value: str | int, *, field_name: str, source_id: str | None = None) -> Decimal:
    try:
        return parse_money(value, field_name=field_name)
    except CaptureValidationError as exc:
        raise purchase_source_input_invalid_error(
            exc.error.message,
            context={"field": field_name, "source_id": source_id},
        ) from exc


def _optional_money(
    value: str | int | None, *, field_name: str, source_id: str | None = None
) -> Decimal | None:
    if value is None:
        return None
    return _money(value, field_name=field_name, source_id=source_id)


def _parse_coupon(
    state: str | None, amount: str | int | None, code: str | None, *, source_id: str | None
) -> Coupon | None:
    if state is None:
        if amount is not None or code is not None:
            raise purchase_source_input_invalid_error(
                "coupon_state é obrigatório quando cupom é informado",
                context={"field": "coupon_state", "source_id": source_id},
            )
        return None
    try:
        coupon_state = CouponState(state)
    except ValueError as exc:
        raise purchase_source_input_invalid_error(
            "coupon_state inválido",
            context={
                "field": "coupon_state",
                "source_id": source_id,
                "allowed": [item.value for item in CouponState],
            },
        ) from exc
    return Coupon(
        state=coupon_state,
        amount=_optional_money(amount, field_name="coupon_amount", source_id=source_id),
        code=_clean(code),
    )


def _parse_conditions(conditions: Mapping[str, str], *, source_id: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_key, raw_value in conditions.items():
        key = sanitize_single_line(str(raw_key))
        if not key:
            raise purchase_source_input_invalid_error(
                "condição comparável sem chave",
                context={"field": "conditions", "source_id": source_id},
            )
        parsed[key] = sanitize_single_line(str(raw_value))
    return parsed


def _parse_url(url: str | None, *, source_id: str | None) -> str | None:
    try:
        return validate_source_url(url)
    except CaptureValidationError as exc:
        raise purchase_source_input_invalid_error(
            exc.error.message, context={"field": "url", "source_id": source_id}
        ) from exc


def _parse_alternative(alternative: PurchaseSourceAlternativeContract) -> PurchaseSource:
    source_id = sanitize_single_line(alternative.source_id)
    if not source_id:
        raise purchase_source_input_invalid_error(
            "source_id é obrigatório", context={"field": "source_id"}
        )
    return PurchaseSource(
        source_id=source_id,
        price=_money(alternative.price, field_name="price", source_id=source_id),
        marketplace=None if alternative.marketplace is None else alternative.marketplace.value,
        url=_parse_url(alternative.url, source_id=source_id),
        shipping_cost=_optional_money(
            alternative.shipping_cost, field_name="shipping_cost", source_id=source_id
        ),
        coupon=_parse_coupon(
            alternative.coupon_state,
            alternative.coupon_amount,
            alternative.coupon_code,
            source_id=source_id,
        )
        or Coupon(),
        product_equivalence_id=_clean(alternative.product_equivalence_id),
        conditions=_parse_conditions(alternative.conditions, source_id=source_id),
        affiliate_commission=_optional_money(
            alternative.affiliate_commission,
            field_name="affiliate_commission",
            source_id=source_id,
        ),
    )


def build_purchase_source_router(engine: Engine, policy: PurchaseSourcePolicy) -> APIRouter:
    """Build the Purchase Source router wired to the SQLite store and policy."""

    router = APIRouter(tags=["purchase-source"])
    service = PurchaseSourceService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        store=SqlAlchemyPurchaseSourceDecisionRepository(engine=engine),
        policy=policy,
    )

    @router.post("/candidates/{candidate_id}/purchase-source", status_code=201)
    def decide_purchase_source(
        candidate_id: str,
        payload: PurchaseSourceRequestContract,
        request: Request,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        record = service.decide(
            candidate_id,
            correlation_id=correlation_id,
            product_equivalence_id=_clean(payload.product_equivalence_id),
            conditions=_parse_conditions(payload.conditions, source_id=None),
            shipping_cost=_optional_money(payload.shipping_cost, field_name="shipping_cost"),
            coupon=_parse_coupon(
                payload.coupon_state,
                payload.coupon_amount,
                payload.coupon_code,
                source_id=None,
            ),
            affiliate_commission=_optional_money(
                payload.affiliate_commission, field_name="affiliate_commission"
            ),
            alternatives=[_parse_alternative(item) for item in payload.alternatives],
        )
        return JSONResponse(
            status_code=201,
            content=record.to_contract(),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/candidates/{candidate_id}/purchase-source")
    def list_purchase_source_decisions(candidate_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        decisions = service.list_decisions(candidate_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": PURCHASE_SOURCE_SCHEMA_VERSION,
                "status": "OK",
                "candidate_id": candidate_id,
                "count": len(decisions),
                "decisions": [decision.to_contract() for decision in decisions],
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_purchase_source_router",
]
