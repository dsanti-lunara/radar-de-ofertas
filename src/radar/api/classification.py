"""Candidate classification public endpoint (RDR-022, RDR-026).

``GET /candidates/{candidate_id}/classification/{brand}`` classifies a persisted
Candidate against the versioned brand taxonomy and returns the canonical
category, priority, approved Brand Fit, explicit calibration gaps and Hard Rules.
The endpoint is read-only and deterministic, so repeated calls are naturally
idempotent and no commercial side effect is triggered. Structured errors reuse
the shared ``RadarException`` handler registered by the capture boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER
from radar.application.classification_service import ClassificationService
from radar.application.correlation import bind_correlation_id
from radar.domain.taxonomy import (
    Brand,
    BrandTaxonomy,
    classification_input_invalid_error,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository


def _parse_brand(value: str) -> Brand:
    try:
        return Brand(value)
    except ValueError as exc:
        raise classification_input_invalid_error(value) from exc


def build_classification_router(engine: Engine, taxonomy: BrandTaxonomy) -> APIRouter:
    """Build the classification router wired to the SQLite repository."""

    router = APIRouter(tags=["classification"])
    service = ClassificationService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        taxonomy=taxonomy,
    )

    @router.get("/candidates/{candidate_id}/classification/{brand}")
    def classify_candidate(
        candidate_id: str,
        brand: str,
        request: Request,
        taxonomy_version: str | None = None,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        result = service.classify(
            candidate_id,
            _parse_brand(brand),
            taxonomy_version=taxonomy_version,
        )
        return JSONResponse(
            status_code=200,
            content={**result.to_contract(), "correlation_id": correlation_id},
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_classification_router",
]
