"""Public Scheduler boundary: schedules and ticks (RDR-039).

``POST /schedules`` persists a schedule; ``GET /schedules`` and
``GET /schedules/{id}`` read it back; ``POST /schedules/{id}/enable|disable``
toggles it. ``POST /schedules/tick`` evaluates every enabled schedule due now and
``POST /schedules/{id}/tick`` forces one schedule; both create only ``PENDING``
Jobs and return the auditable tick report. Every response is versioned with the
pipeline Correlation ID, so the Scheduler behaviour is observable from here.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import (
    CORRELATION_HEADER,
    ScheduleCreateContract,
)
from radar.application.correlation import bind_correlation_id
from radar.application.schedule_service import ScheduleService
from radar.domain.schedule import SCHEDULE_SCHEMA_VERSION, Schedule, TickResult
from radar.infrastructure.schedule_repository import SqlAlchemyScheduleRepository


def _schedule_response(
    schedule: Schedule, *, correlation_id: str, status: str, status_code: int
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": status, **schedule.to_contract()},
        headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
    )


def _tick_response(
    results: list[TickResult], *, correlation_id: str, ticked_at: str
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            "schema_version": SCHEDULE_SCHEMA_VERSION,
            "status": "TICKED",
            "correlation_id": correlation_id,
            "ticked_at": ticked_at,
            "results": [result.to_contract() for result in results],
        },
        headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
    )


def build_schedule_router(engine: Engine) -> APIRouter:
    """Build the Scheduler router wired to the SQLite repository."""

    router = APIRouter(tags=["schedules"])
    service = ScheduleService(repository=SqlAlchemyScheduleRepository(engine=engine))

    @router.post("/schedules", status_code=201)
    def create_schedule(payload: ScheduleCreateContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        schedule = service.create(
            name=payload.name,
            schedule_type=payload.type,
            job_type=payload.job_type,
            priority=payload.priority,
            max_attempts=payload.max_attempts,
            enabled=payload.enabled,
            timezone=payload.timezone,
            interval_seconds=payload.interval_seconds,
            cron=payload.cron,
            quiet_windows=[window.model_dump() for window in payload.quiet_windows],
            lock_name=payload.lock_name,
            payload=payload.payload,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            schema_version=payload.schema_version,
            correlation_id=correlation_id,
        )
        return _schedule_response(
            schedule, correlation_id=correlation_id, status="CREATED", status_code=201
        )

    @router.get("/schedules")
    def list_schedules(request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        schedules = service.list()
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": SCHEDULE_SCHEMA_VERSION,
                "correlation_id": correlation_id,
                "schedules": [schedule.to_contract() for schedule in schedules],
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.post("/schedules/tick")
    def tick_due(request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        now = service.clock()
        results = service.tick_due(correlation_id=correlation_id, now=now)
        return _tick_response(results, correlation_id=correlation_id, ticked_at=now.isoformat())

    @router.get("/schedules/{schedule_id}")
    def get_schedule(schedule_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        schedule = service.get(schedule_id)
        return _schedule_response(
            schedule, correlation_id=correlation_id, status="OK", status_code=200
        )

    @router.post("/schedules/{schedule_id}/tick")
    def tick_schedule(schedule_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        now = service.clock()
        result = service.tick_schedule(schedule_id, correlation_id=correlation_id, now=now)
        return _tick_response([result], correlation_id=correlation_id, ticked_at=now.isoformat())

    @router.post("/schedules/{schedule_id}/enable")
    def enable_schedule(schedule_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        schedule = service.set_enabled(schedule_id, enabled=True, correlation_id=correlation_id)
        return _schedule_response(
            schedule, correlation_id=correlation_id, status="ENABLED", status_code=200
        )

    @router.post("/schedules/{schedule_id}/disable")
    def disable_schedule(schedule_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        schedule = service.set_enabled(schedule_id, enabled=False, correlation_id=correlation_id)
        return _schedule_response(
            schedule, correlation_id=correlation_id, status="DISABLED", status_code=200
        )

    return router


__all__ = [
    "build_schedule_router",
]
