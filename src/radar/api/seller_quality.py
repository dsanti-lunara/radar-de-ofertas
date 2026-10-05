"""Candidate Seller Quality public endpoint (RDR-024).

``GET /candidates/{candidate_id}/seller-quality`` evaluates the deterministic
Seller Quality breakdown from the Candidate's persisted seller facts and the
active versioned normalization. The endpoint is read-only and idempotent:
repeated calls with the same facts and signals yield the same result and no
commercial side effect is triggered.

Signals the manual capture does not persist yet (marketplace reputation and
official/trusted status) can be supplied as optional query parameters. They are
validated here and never trusted blindly; malformed input fails with a structured
error while semantically invalid/contradictory values are reported as warnings by
the domain. Structured errors reuse the shared ``RadarException`` handler
registered by the capture boundary.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER
from radar.application.correlation import bind_correlation_id
from radar.application.seller_quality_service import (
    ORIGIN_EVALUATION_INPUT,
    SellerQualityService,
)
from radar.domain.capture import sanitize_single_line
from radar.domain.seller_quality import (
    SellerQualityNormalization,
    SellerSignal,
    seller_quality_input_invalid_error,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository

_INTEGER = re.compile(r"^[+-]?\d+$")
_TRUSTED = {"true": True, "false": False}


def _parse_reputation(value: str | None) -> SellerSignal[str] | None:
    if value is None:
        return None
    cleaned = sanitize_single_line(value)
    if not cleaned:
        raise seller_quality_input_invalid_error(
            "reputation não pode ser vazia", context={"field": "reputation"}
        )
    return SellerSignal(value=cleaned, source=ORIGIN_EVALUATION_INPUT)


def _parse_rating(value: str | None) -> SellerSignal[Decimal] | None:
    if value is None:
        return None
    try:
        amount = Decimal(value.strip())
    except (InvalidOperation, ValueError) as exc:
        raise seller_quality_input_invalid_error(
            "rating inválido", context={"field": "rating"}
        ) from exc
    if not amount.is_finite():
        raise seller_quality_input_invalid_error(
            "rating deve ser finito", context={"field": "rating"}
        )
    return SellerSignal(value=amount, source=ORIGIN_EVALUATION_INPUT)


def _parse_sales_count(value: str | None) -> SellerSignal[int] | None:
    if value is None:
        return None
    text = value.strip()
    if not _INTEGER.match(text):
        raise seller_quality_input_invalid_error(
            "sales_count deve ser inteiro", context={"field": "sales_count"}
        )
    return SellerSignal(value=int(text), source=ORIGIN_EVALUATION_INPUT)


def _parse_trusted(value: str | None) -> SellerSignal[bool] | None:
    if value is None:
        return None
    key = value.strip().lower()
    if key not in _TRUSTED:
        raise seller_quality_input_invalid_error(
            "trusted deve ser true ou false", context={"field": "trusted"}
        )
    return SellerSignal(value=_TRUSTED[key], source=ORIGIN_EVALUATION_INPUT)


def build_seller_quality_router(
    engine: Engine, normalization: SellerQualityNormalization
) -> APIRouter:
    """Build the Seller Quality router wired to the SQLite repository."""

    router = APIRouter(tags=["seller-quality"])
    service = SellerQualityService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        normalization=normalization,
    )

    @router.get("/candidates/{candidate_id}/seller-quality")
    def evaluate_seller_quality(
        candidate_id: str,
        request: Request,
        reputation: str | None = None,
        rating: str | None = None,
        sales_count: str | None = None,
        trusted: str | None = None,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        result = service.evaluate(
            candidate_id,
            reputation=_parse_reputation(reputation),
            rating=_parse_rating(rating),
            sales_count=_parse_sales_count(sales_count),
            trusted=_parse_trusted(trusted),
        )
        return JSONResponse(
            status_code=200,
            content={**result.to_contract(), "correlation_id": correlation_id},
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_seller_quality_router",
]
