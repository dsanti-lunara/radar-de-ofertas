"""Candidate Demand public endpoint (RDR-025).

``GET /candidates/{candidate_id}/demand`` evaluates the deterministic,
category-versioned Demand breakdown from the Candidate's persisted facts
(raw category and sales count) and the active per-category normalization. The
endpoint is read-only and idempotent: repeated calls with the same facts and
signals yield the same result and no commercial side effect is triggered.

Signals the manual capture does not persist yet (rating count, trend, affiliate
portal signal and badges) can be supplied as optional query parameters. They are
validated here and never trusted blindly; malformed input fails with a structured
error while absent or uncalibrated signals are reported as warnings by the
domain. Structured errors reuse the shared ``RadarException`` handler registered
by the capture boundary.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER
from radar.application.correlation import bind_correlation_id
from radar.application.demand_service import (
    ORIGIN_EVALUATION_INPUT,
    DemandService,
)
from radar.domain.capture import sanitize_single_line
from radar.domain.demand import (
    DemandNormalization,
    DemandSignal,
    demand_input_invalid_error,
)
from radar.domain.taxonomy import BrandTaxonomy
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository

_INTEGER = re.compile(r"^[+-]?\d+$")


def _parse_rating_count(value: str | None) -> DemandSignal[int] | None:
    if value is None:
        return None
    text = value.strip()
    if not _INTEGER.match(text):
        raise demand_input_invalid_error(
            "rating_count deve ser inteiro", context={"field": "rating_count"}
        )
    amount = int(text)
    if amount < 0:
        raise demand_input_invalid_error(
            "rating_count não pode ser negativo", context={"field": "rating_count"}
        )
    return DemandSignal(value=amount, source=ORIGIN_EVALUATION_INPUT)


def _parse_label(value: str | None, *, field_name: str) -> DemandSignal[str] | None:
    if value is None:
        return None
    cleaned = sanitize_single_line(value)
    if not cleaned:
        raise demand_input_invalid_error(
            f"{field_name} não pode ser vazio", context={"field": field_name}
        )
    return DemandSignal(value=cleaned, source=ORIGIN_EVALUATION_INPUT)


def _parse_badges(value: str | None) -> DemandSignal[tuple[str, ...]] | None:
    if value is None:
        return None
    items = tuple(cleaned for item in value.split(",") if (cleaned := sanitize_single_line(item)))
    if not items:
        raise demand_input_invalid_error("badges não pode ser vazio", context={"field": "badges"})
    return DemandSignal(value=items, source=ORIGIN_EVALUATION_INPUT)


def build_demand_router(
    engine: Engine,
    taxonomy: BrandTaxonomy,
    normalization: DemandNormalization,
) -> APIRouter:
    """Build the Demand router wired to the SQLite repository and taxonomy."""

    router = APIRouter(tags=["demand"])
    service = DemandService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        taxonomy=taxonomy,
        normalization=normalization,
    )

    @router.get("/candidates/{candidate_id}/demand")
    def evaluate_demand(
        candidate_id: str,
        request: Request,
        rating_count: str | None = None,
        trend: str | None = None,
        affiliate_portal: str | None = None,
        badges: str | None = None,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        result = service.evaluate(
            candidate_id,
            rating_count=_parse_rating_count(rating_count),
            trend=_parse_label(trend, field_name="trend"),
            affiliate_portal=_parse_label(affiliate_portal, field_name="affiliate_portal"),
            badges=_parse_badges(badges),
        )
        return JSONResponse(
            status_code=200,
            content={**result.to_contract(), "correlation_id": correlation_id},
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_demand_router",
]
