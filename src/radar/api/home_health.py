"""Home health overview boundary (RDR-057, SPEC-07).

``GET /health/overview`` is the read model consumed by the Control Center Home
health strip. Unlike the liveness/readiness contract of ``GET /health`` (which
fails closed with HTTP 503), the overview is a diagnostic representation: it
answers HTTP 200 with the versioned body so the UI can render the aggregate
``status`` and every per-capability state without conflating the HTTP status
with a dependency fault. The body still carries the Correlation ID and the
``Cache-Control: no-store`` header.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER
from radar.application.correlation import bind_correlation_id
from radar.application.health_service import HealthService
from radar.application.home_health_service import HomeHealthService
from radar.infrastructure.operations_repository import SqlAlchemyOperationsRepository


def build_home_health_router(engine: Engine, health_service: HealthService) -> APIRouter:
    """Build the Home health overview router wired to the SQLite store."""

    router = APIRouter(tags=["health"])
    service = HomeHealthService(
        health_service=health_service,
        integrations=SqlAlchemyOperationsRepository(engine=engine),
    )

    @router.get("/health/overview")
    def home_health(request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        overview = service.evaluate(correlation_id)
        return JSONResponse(
            status_code=200,
            content=overview.to_contract(),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_home_health_router",
]
