"""Startup Recovery Manager public boundary (RDR-042).

``POST /recovery`` runs recovery and returns the auditable report; ``GET
/recovery`` reads the durable runtime/shutdown marker; ``POST
/recovery/clean-shutdown`` records the clean-shutdown marker so the next startup
is not treated as an unclean shutdown. Every response carries the versioned
contract and the pipeline Correlation ID, so the recovery outcome is observable
from here.

Safe reading/diagnostic/recovery never depend on the operational kill switch
(AUT-317); this boundary performs no external side effect.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import (
    CORRELATION_HEADER,
    RecoveryRunContract,
    RecoveryShutdownContract,
)
from radar.application.correlation import bind_correlation_id
from radar.application.recovery_service import RecoveryService
from radar.application.schedule_service import ScheduleService
from radar.domain.recovery import RECOVERY_SCHEMA_VERSION
from radar.infrastructure.recovery_repository import SqlAlchemyRecoveryRepository
from radar.infrastructure.schedule_repository import SqlAlchemyScheduleRepository


def _headers(correlation_id: str) -> dict[str, str]:
    return {CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"}


def build_recovery_router(engine: Engine) -> APIRouter:
    """Build the Recovery Manager router wired to the SQLite store."""

    router = APIRouter(tags=["recovery"])
    service = RecoveryService(
        store=SqlAlchemyRecoveryRepository(engine=engine),
        schedule_service=ScheduleService(repository=SqlAlchemyScheduleRepository(engine=engine)),
    )

    @router.post("/recovery")
    def run_recovery(payload: RecoveryRunContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        report = service.run_recovery(correlation_id=correlation_id, trigger=payload.trigger)
        return JSONResponse(
            status_code=200,
            content=report.to_contract(),
            headers=_headers(correlation_id),
        )

    @router.get("/recovery")
    def get_recovery(request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        state = service.status()
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": RECOVERY_SCHEMA_VERSION,
                "status": "OK" if state is not None else "NOT_RECORDED",
                "state": None if state is None else state.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.post("/recovery/clean-shutdown")
    def record_clean_shutdown(payload: RecoveryShutdownContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        state = service.record_clean_shutdown(correlation_id=correlation_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": RECOVERY_SCHEMA_VERSION,
                "status": "CLEAN",
                "state": state.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    return router


__all__ = [
    "build_recovery_router",
]
