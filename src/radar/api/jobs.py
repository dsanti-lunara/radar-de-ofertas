"""Public Job queue and logical lock endpoints (RDR-034..036).

``POST /jobs`` enqueues a ``PENDING`` job; ``POST /jobs/claim`` grants a single
expiring lease; ``POST /jobs/{id}/start`` and ``POST /jobs/{id}/complete`` are
owned by that lease; ``GET /jobs/{id}`` reads the persisted state. Logical locks
have their own ``POST /locks`` / ``DELETE /locks/{name}`` boundary. Every
response is versioned and the persisted behaviour is observable from here.

Structured errors reuse the shared ``RadarException``/validation handlers
registered by the capture boundary; the validation handler classifies job/lock
paths as ``RAD-WF-006``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import (
    CORRELATION_HEADER,
    JobClaimContract,
    JobEnqueueContract,
    JobWorkerContract,
    LockAcquireContract,
)
from radar.application.correlation import bind_correlation_id
from radar.application.job_service import JobService
from radar.domain.job import JOB_SCHEMA_VERSION, Job, Lock
from radar.infrastructure.job_repository import SqlAlchemyJobRepository


def _job_response(job: Job, *, correlation_id: str, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=job.to_contract(),
        headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
    )


def _lock_response(lock: Lock, *, correlation_id: str, status_code: int = 201) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "ACQUIRED", **lock.to_contract()},
        headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
    )


def build_job_router(engine: Engine) -> APIRouter:
    """Build the Job/lock router wired to the SQLite repository."""

    router = APIRouter(tags=["jobs"])
    service = JobService(repository=SqlAlchemyJobRepository(engine=engine))

    @router.post("/jobs", status_code=201)
    def enqueue_job(payload: JobEnqueueContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        job = service.enqueue(
            job_type=payload.type,
            correlation_id=correlation_id,
            payload=payload.payload,
            priority=payload.priority,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            available_at=payload.available_at,
            max_attempts=payload.max_attempts,
            schema_version=payload.schema_version,
        )
        return _job_response(job, correlation_id=correlation_id, status_code=201)

    @router.post("/jobs/claim")
    def claim_job(payload: JobClaimContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        job = service.claim(worker_id=payload.worker_id, lease_seconds=payload.lease_seconds)
        return _job_response(job, correlation_id=correlation_id)

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        job = service.get(job_id)
        return _job_response(job, correlation_id=correlation_id)

    @router.post("/jobs/{job_id}/start")
    def start_job(job_id: str, payload: JobWorkerContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        job = service.start(job_id, worker_id=payload.worker_id)
        return _job_response(job, correlation_id=correlation_id)

    @router.post("/jobs/{job_id}/complete")
    def complete_job(job_id: str, payload: JobWorkerContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        job = service.complete(job_id, worker_id=payload.worker_id)
        return _job_response(job, correlation_id=correlation_id)

    @router.post("/locks", status_code=201)
    def acquire_lock(payload: LockAcquireContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        lock = service.acquire_lock(
            name=payload.name,
            owner=payload.owner,
            ttl_seconds=payload.ttl_seconds,
            correlation_id=correlation_id,
        )
        return _lock_response(lock, correlation_id=correlation_id)

    @router.delete("/locks/{name}")
    def release_lock(
        name: str,
        request: Request,
        owner: str,
        schema_version: str = JOB_SCHEMA_VERSION,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        service.release_lock(name, owner=owner)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": schema_version,
                "status": "RELEASED",
                "name": name,
                "owner": owner,
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_job_router",
]
