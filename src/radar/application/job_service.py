"""Job orchestration: enqueue, claim/lease, complete and logical locks.

The service validates the public inputs (schema_version, Job type, priority,
payload, worker/lease) and delegates the atomic transitions to a
:class:`JobStore` port. Everything the domain needs is framework-free; the
SQLAlchemy implementation lives in infrastructure (AUT-397).

This ticket (RDR-034..036) covers enqueue, single-lease claim, lease expiry,
completion by the lease owner and logical locks. Retry/backoff, Dead Jobs,
scheduling and crash recovery build on this model in their own tickets.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.job import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    JOB_SCHEMA_VERSION,
    Job,
    Lock,
    create_job,
    job_not_found_error,
    require_lease_seconds,
    require_worker_id,
)
from radar.domain.retry import (
    APPROVED_RETRY_POLICY,
    JobFailureResult,
    RetryPolicy,
    require_error_code,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class JobStore(Protocol):
    """Persistence port for the durable Job queue and logical locks."""

    def enqueue(self, job: Job) -> Job: ...

    def get(self, job_id: str) -> Job | None: ...

    def claim(self, *, worker_id: str, lease_seconds: int, now: datetime) -> Job: ...

    def start(self, job_id: str, *, worker_id: str, now: datetime) -> Job: ...

    def complete(self, job_id: str, *, worker_id: str, now: datetime) -> Job: ...

    def fail(
        self,
        job_id: str,
        *,
        worker_id: str,
        error_code: str,
        policy: RetryPolicy,
        now: datetime,
    ) -> JobFailureResult: ...

    def acquire_lock(
        self,
        *,
        name: str,
        owner: str,
        ttl_seconds: int,
        now: datetime,
        correlation_id: str | None = None,
    ) -> Lock: ...

    def release_lock(self, name: str, *, owner: str, now: datetime) -> None: ...

    def get_lock(self, name: str) -> Lock | None: ...


@dataclass(slots=True)
class JobService:
    """Validate and drive the persistent Job queue through the public boundary."""

    repository: JobStore
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory
    default_lease_seconds: int = DEFAULT_LEASE_SECONDS
    retry_policy: RetryPolicy = APPROVED_RETRY_POLICY

    def enqueue(
        self,
        *,
        job_type: object,
        correlation_id: object,
        payload: Mapping[str, Any] | None = None,
        priority: object = 0,
        entity_type: str | None = None,
        entity_id: str | None = None,
        available_at: datetime | None = None,
        max_attempts: object = DEFAULT_MAX_ATTEMPTS,
        schema_version: object = JOB_SCHEMA_VERSION,
    ) -> Job:
        """Create and persist a ``PENDING`` job (RDR-034)."""

        now = self.clock()
        job = create_job(
            job_type=job_type,
            correlation_id=correlation_id,
            now=now,
            payload=payload,
            priority=priority,
            entity_type=entity_type,
            entity_id=entity_id,
            available_at=available_at,
            max_attempts=max_attempts,
            schema_version=schema_version,
            id_factory=self.id_factory,
        )
        return self.repository.enqueue(job)

    def claim(self, *, worker_id: object, lease_seconds: object = None) -> Job:
        """Claim a single lease for the given worker (RDR-035)."""

        resolved_worker = require_worker_id(worker_id)
        resolved_lease = require_lease_seconds(
            self.default_lease_seconds if lease_seconds is None else lease_seconds
        )
        return self.repository.claim(
            worker_id=resolved_worker, lease_seconds=resolved_lease, now=self.clock()
        )

    def start(self, job_id: str, *, worker_id: object) -> Job:
        """Transition the worker's claimed job to ``RUNNING``."""

        return self.repository.start(
            job_id, worker_id=require_worker_id(worker_id), now=self.clock()
        )

    def complete(self, job_id: str, *, worker_id: object) -> Job:
        """Confirm the worker's owned execution as ``SUCCESS``."""

        return self.repository.complete(
            job_id, worker_id=require_worker_id(worker_id), now=self.clock()
        )

    def fail(self, job_id: str, *, worker_id: object, error_code: object) -> JobFailureResult:
        """Report a job failure and classify it into retry/Dead/Failed (RDR-037/038)."""

        return self.repository.fail(
            job_id,
            worker_id=require_worker_id(worker_id),
            error_code=require_error_code(error_code),
            policy=self.retry_policy,
            now=self.clock(),
        )

    def get(self, job_id: str) -> Job:
        """Return a persisted job, raising a structured not-found error."""

        job = self.repository.get(job_id)
        if job is None:
            raise job_not_found_error(job_id)
        return job

    def acquire_lock(
        self,
        *,
        name: object,
        owner: object,
        ttl_seconds: object = None,
        correlation_id: object = None,
    ) -> Lock:
        """Acquire or renew a logical lock with an expiration (RDR-036)."""

        resolved_ttl = require_lease_seconds(
            self.default_lease_seconds if ttl_seconds is None else ttl_seconds,
            field_name="ttl_seconds",
        )
        return self.repository.acquire_lock(
            name=str(name),
            owner=require_worker_id(owner),
            ttl_seconds=resolved_ttl,
            now=self.clock(),
            correlation_id=None if correlation_id is None else str(correlation_id),
        )

    def release_lock(self, name: str, *, owner: object) -> None:
        """Release a logical lock owned by the caller."""

        self.repository.release_lock(name, owner=require_worker_id(owner), now=self.clock())

    def get_lock(self, name: str) -> Lock | None:
        """Return the current lock row (active or expired) or ``None``."""

        return self.repository.get_lock(name)


__all__ = [
    "JobService",
    "JobStore",
]
