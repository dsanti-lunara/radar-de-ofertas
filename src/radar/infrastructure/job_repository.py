"""SQLAlchemy implementation of the persistent Job queue and logical locks.

The claim is the critical section: it is expressed as a **single** ``UPDATE`` with
a claimable subquery and a ``RETURNING`` clause, so under SQLite's single-writer
guarantee two concurrent workers can never obtain the same lease (RDR-035,
AUT-121). Every transition also writes an audit event in the same transaction, so
the job lifecycle is observable and traceable from the public boundary
(AUT-040, AUT-141).

Retry/backoff, Dead Jobs, scheduling and crash recovery are separate tickets; the
repository only provides the durable queue plus claim/lease/lock behaviour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.domain.audit import (
    HUMAN_ACTION_CREATED,
    JOB_CLAIMED,
    JOB_DEAD,
    JOB_ENQUEUED,
    JOB_FAILED,
    JOB_RETRY_SCHEDULED,
    JOB_STARTED,
    JOB_SUCCEEDED,
    LOCK_ACQUIRED,
    LOCK_RELEASED,
)
from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.human_action import build_human_action
from radar.domain.job import (
    AUDIT_SOURCE_JOB,
    ENTITY_JOB,
    Job,
    JobStatus,
    JobType,
    Lock,
    complete_job,
    job_lease_not_held_error,
    job_not_claimable_error,
    job_not_found_error,
    lock_unavailable_error,
    start_job,
)
from radar.domain.retry import (
    FailureAction,
    JobFailureResult,
    RetryPolicy,
    apply_failure,
    resolve_failure,
)
from radar.infrastructure.human_action_repository import human_action_to_row
from radar.infrastructure.models import AuditEventRow, JobLockRow, JobRow


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment)


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


@dataclass(slots=True)
class SqlAlchemyJobRepository:
    """Persist and claim Jobs, and acquire/release logical locks, on SQLite."""

    engine: Engine
    id_factory: IdFactory = default_id_factory

    # -- Jobs ---------------------------------------------------------------

    def enqueue(self, job: Job) -> Job:
        """Persist a new ``PENDING`` job and its ``JOB_ENQUEUED`` audit event."""

        with Session(self.engine) as session, session.begin():
            session.add(_job_to_row(job))
            session.flush()
            session.add(
                _audit_row(
                    job_id=job.id,
                    event_type=JOB_ENQUEUED,
                    correlation_id=job.correlation_id,
                    recorded_at=job.created_at,
                    payload={
                        "type": job.type.value,
                        "priority": job.priority,
                        "status": job.status.value,
                        "attempts": job.attempts,
                    },
                    id_factory=self.id_factory,
                )
            )
        return job

    def get(self, job_id: str) -> Job | None:
        """Return a job by id or ``None`` when it does not exist."""

        with Session(self.engine) as session:
            row = session.get(JobRow, job_id)
            return None if row is None else _job_from_row(row)

    def claim(self, *, worker_id: str, lease_seconds: int, now: datetime) -> Job:
        """Atomically claim the highest-priority claimable job for one worker.

        A ``PENDING`` job becomes available at ``available_at``; a
        ``CLAIMED``/``RUNNING`` job with an expired lease is recoverable. The
        conditional ``UPDATE`` grants a single valid lease, sets the lease
        expiration and increments ``attempts`` (RDR-035, AUT-133, AUT-140).
        """

        now_utc = _utc(now)
        now_iso = _iso(now_utc)
        expiry_iso = _iso(now_utc + timedelta(seconds=lease_seconds))
        claimable = (
            select(JobRow.id)
            .where(
                or_(
                    and_(
                        JobRow.status.in_([JobStatus.PENDING.value, JobStatus.RETRY_WAIT.value]),
                        JobRow.available_at <= now_iso,
                    ),
                    and_(
                        JobRow.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
                        JobRow.lease_expires_at.is_not(None),
                        JobRow.lease_expires_at <= now_iso,
                    ),
                )
            )
            .order_by(
                JobRow.priority.desc(),
                JobRow.available_at.asc(),
                JobRow.created_at.asc(),
                JobRow.id.asc(),
            )
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            update(JobRow)
            .where(JobRow.id == claimable)
            .values(
                status=JobStatus.CLAIMED.value,
                locked_by=worker_id,
                locked_at=now_iso,
                lease_expires_at=expiry_iso,
                attempts=JobRow.attempts + 1,
                updated_at=now_iso,
            )
            .returning(JobRow.id)
        )
        with Session(self.engine) as session, session.begin():
            claimed_id = session.execute(statement).scalar_one_or_none()
            if claimed_id is None:
                raise job_not_claimable_error(context={"worker_id": worker_id})
            row = session.get(JobRow, claimed_id)
            if row is None:  # pragma: no cover - defensive: RETURNING id always exists
                raise job_not_found_error(str(claimed_id))
            job = _job_from_row(row)
            session.add(
                _audit_row(
                    job_id=job.id,
                    event_type=JOB_CLAIMED,
                    correlation_id=job.correlation_id,
                    recorded_at=now_utc,
                    payload={
                        "worker_id": worker_id,
                        "attempts": job.attempts,
                        "lease_expires_at": expiry_iso,
                    },
                    id_factory=self.id_factory,
                )
            )
        return job

    def start(self, job_id: str, *, worker_id: str, now: datetime) -> Job:
        """Transition a job the worker owns to ``RUNNING`` (idempotent for owner)."""

        now_utc = _utc(now)
        with Session(self.engine) as session, session.begin():
            row = session.get(JobRow, job_id)
            if row is None:
                raise job_not_found_error(job_id)
            job = _job_from_row(row)
            if (
                job.status is JobStatus.RUNNING
                and job.locked_by == worker_id
                and job.lease_is_active(now_utc)
            ):
                return job
            transitioned = start_job(job, worker_id=worker_id, now=now_utc)
            updated_id = session.execute(
                update(JobRow)
                .where(
                    JobRow.id == job_id,
                    JobRow.locked_by == worker_id,
                    JobRow.status == job.status.value,
                    JobRow.lease_expires_at == row.lease_expires_at,
                )
                .values(status=transitioned.status.value, updated_at=_iso(now_utc))
                .returning(JobRow.id)
            ).scalar_one_or_none()
            if updated_id is None:
                raise job_lease_not_held_error(
                    job_id,
                    worker_id=worker_id,
                    reason="lease_changed",
                    holder=row.locked_by,
                )
            session.add(
                _audit_row(
                    job_id=job_id,
                    event_type=JOB_STARTED,
                    correlation_id=job.correlation_id,
                    recorded_at=now_utc,
                    payload={"worker_id": worker_id, "attempts": job.attempts},
                    id_factory=self.id_factory,
                )
            )
        return transitioned

    def complete(self, job_id: str, *, worker_id: str, now: datetime) -> Job:
        """Transition a job the worker owns to ``SUCCESS`` (idempotent for owner).

        A different worker can never confirm an execution it does not own, even
        after the lease expired (AUT-140).
        """

        now_utc = _utc(now)
        with Session(self.engine) as session, session.begin():
            row = session.get(JobRow, job_id)
            if row is None:
                raise job_not_found_error(job_id)
            job = _job_from_row(row)
            transitioned = complete_job(job, worker_id=worker_id, now=now_utc)
            if transitioned is job:
                return job
            updated_id = session.execute(
                update(JobRow)
                .where(
                    JobRow.id == job_id,
                    JobRow.locked_by == worker_id,
                    JobRow.status == job.status.value,
                    JobRow.lease_expires_at == row.lease_expires_at,
                )
                .values(
                    status=transitioned.status.value,
                    lease_expires_at=None,
                    updated_at=_iso(now_utc),
                )
                .returning(JobRow.id)
            ).scalar_one_or_none()
            if updated_id is None:
                raise job_lease_not_held_error(
                    job_id,
                    worker_id=worker_id,
                    reason="lease_changed",
                    holder=row.locked_by,
                )
            session.add(
                _audit_row(
                    job_id=job_id,
                    event_type=JOB_SUCCEEDED,
                    correlation_id=job.correlation_id,
                    recorded_at=now_utc,
                    payload={"worker_id": worker_id, "attempts": job.attempts},
                    id_factory=self.id_factory,
                )
            )
        return transitioned

    def fail(
        self,
        job_id: str,
        *,
        worker_id: str,
        error_code: str,
        policy: RetryPolicy,
        now: datetime,
    ) -> JobFailureResult:
        """Classify a reported failure and persist retry/Dead/Failed atomically.

        The worker must hold the current lease (AUT-140). ``TRANSIENT`` schedules
        a retry with the configured backoff until the attempt budget is
        exhausted; ``PERMANENT`` fails without retry; ``HUMAN_REQUIRED`` and
        exhaustion route to ``DEAD`` and create an auditable HumanAction in the
        **same transaction** as the job transition, referencing the existing
        entity and never recreating it (RDR-037, RDR-038, RDR-040).
        """

        now_utc = _utc(now)
        with Session(self.engine) as session, session.begin():
            row = session.get(JobRow, job_id)
            if row is None:
                raise job_not_found_error(job_id)
            job = _job_from_row(row)
            resolution = resolve_failure(job, error_code=error_code, now=now_utc, policy=policy)
            transitioned = apply_failure(job, resolution, worker_id=worker_id, now=now_utc)
            updated_id = session.execute(
                update(JobRow)
                .where(
                    JobRow.id == job_id,
                    JobRow.locked_by == worker_id,
                    JobRow.status == job.status.value,
                    JobRow.lease_expires_at == row.lease_expires_at,
                )
                .values(
                    status=transitioned.status.value,
                    available_at=_iso(transitioned.available_at),
                    locked_by=None,
                    locked_at=None,
                    lease_expires_at=None,
                    updated_at=_iso(now_utc),
                )
                .returning(JobRow.id)
            ).scalar_one_or_none()
            if updated_id is None:
                raise job_lease_not_held_error(
                    job_id,
                    worker_id=worker_id,
                    reason="lease_changed",
                    holder=row.locked_by,
                )
            human_action = None
            if resolution.human_action_type is not None:
                human_action = build_human_action(
                    action_type=resolution.human_action_type,
                    entity_type=job.entity_type or ENTITY_JOB,
                    entity_id=job.entity_id or job.id,
                    reason=resolution.reason,
                    error_code=error_code,
                    correlation_id=job.correlation_id,
                    now=now_utc,
                    id_factory=self.id_factory,
                )
                session.add(human_action_to_row(human_action))
                session.add(
                    _audit_row(
                        job_id=human_action.id,
                        event_type=HUMAN_ACTION_CREATED,
                        correlation_id=job.correlation_id,
                        recorded_at=now_utc,
                        payload={
                            "action_type": human_action.action_type.value,
                            "reason": human_action.reason,
                            "entity_type": human_action.entity_type,
                            "entity_id": human_action.entity_id,
                        },
                        entity_type="human_action",
                        id_factory=self.id_factory,
                    )
                )
            event_type = {
                FailureAction.RETRY_WAIT: JOB_RETRY_SCHEDULED,
                FailureAction.DEAD: JOB_DEAD,
                FailureAction.FAILED: JOB_FAILED,
            }[resolution.action]
            payload = {
                "worker_id": worker_id,
                "error_code": error_code,
                "failure_class": resolution.failure_class.value,
                "reason": resolution.reason,
                "attempts": transitioned.attempts,
            }
            if resolution.delay_seconds is not None:
                payload["delay_seconds"] = resolution.delay_seconds
            session.add(
                _audit_row(
                    job_id=job_id,
                    event_type=event_type,
                    correlation_id=job.correlation_id,
                    recorded_at=now_utc,
                    payload=payload,
                    id_factory=self.id_factory,
                )
            )
        return JobFailureResult(
            job=transitioned,
            resolution=resolution,
            error_code=error_code,
            human_action=human_action,
        )

    # -- Locks --------------------------------------------------------------

    def acquire_lock(
        self,
        *,
        name: str,
        owner: str,
        ttl_seconds: int,
        now: datetime,
        correlation_id: str | None = None,
    ) -> Lock:
        """Acquire or renew a logical lock, failing closed when another holds it.

        An active lock owned by another worker yields ``RAD-WF-004``; an expired
        lock is taken over. Re-acquiring with the same owner renews the TTL
        (idempotent).
        """

        now_utc = _utc(now)
        expiry = now_utc + timedelta(seconds=ttl_seconds)
        try:
            with Session(self.engine) as session, session.begin():
                row = session.get(JobLockRow, name)
                if row is None:
                    session.add(
                        JobLockRow(
                            name=name,
                            owner=owner,
                            acquired_at=_iso(now_utc),
                            expires_at=_iso(expiry),
                            correlation_id=correlation_id,
                            updated_at=_iso(now_utc),
                        )
                    )
                    session.add(
                        _audit_row(
                            job_id=name,
                            event_type=LOCK_ACQUIRED,
                            correlation_id=correlation_id or name,
                            recorded_at=now_utc,
                            payload={"owner": owner, "expires_at": _iso(expiry)},
                            entity_type="lock",
                            id_factory=self.id_factory,
                        )
                    )
                    return Lock(
                        name=name,
                        owner=owner,
                        acquired_at=now_utc,
                        expires_at=expiry,
                        correlation_id=correlation_id,
                    )
                current = _lock_from_row(row)
                if current.is_active(now_utc) and current.owner != owner:
                    raise lock_unavailable_error(
                        name,
                        owner=owner,
                        reason="held_by_other",
                        holder=current.owner,
                        expires_at=current.expires_at,
                    )
                if not current.is_active(now_utc) and current.owner != owner:
                    # Taking over an expired lock is auditable.
                    session.add(
                        _audit_row(
                            job_id=name,
                            event_type=LOCK_ACQUIRED,
                            correlation_id=correlation_id or name,
                            recorded_at=now_utc,
                            payload={
                                "owner": owner,
                                "previous_owner": current.owner,
                                "took_over_expired": True,
                                "expires_at": _iso(expiry),
                            },
                            entity_type="lock",
                            id_factory=self.id_factory,
                        )
                    )
                row.owner = owner
                row.acquired_at = _iso(now_utc)
                row.expires_at = _iso(expiry)
                row.correlation_id = correlation_id
                row.updated_at = _iso(now_utc)
                return Lock(
                    name=name,
                    owner=owner,
                    acquired_at=now_utc,
                    expires_at=expiry,
                    correlation_id=correlation_id,
                )
        except IntegrityError as exc:
            # A concurrent insert won the race; fail closed as retryable.
            raise lock_unavailable_error(name, owner=owner, reason="concurrent_acquire") from exc

    def release_lock(self, name: str, *, owner: str, now: datetime) -> None:
        """Release a lock, but only when the caller owns it."""

        now_utc = _utc(now)
        with Session(self.engine) as session, session.begin():
            row = session.get(JobLockRow, name)
            if row is None:
                raise lock_unavailable_error(name, owner=owner, reason="not_found")
            current = _lock_from_row(row)
            if current.owner != owner:
                raise lock_unavailable_error(
                    name,
                    owner=owner,
                    reason="not_owner",
                    holder=current.owner,
                    expires_at=current.expires_at,
                )
            session.delete(row)
            session.add(
                _audit_row(
                    job_id=name,
                    event_type=LOCK_RELEASED,
                    correlation_id=current.correlation_id or name,
                    recorded_at=now_utc,
                    payload={"owner": owner},
                    entity_type="lock",
                    id_factory=self.id_factory,
                )
            )

    def get_lock(self, name: str) -> Lock | None:
        """Return the current lock row (active or expired) or ``None``."""

        with Session(self.engine) as session:
            row = session.get(JobLockRow, name)
            return None if row is None else _lock_from_row(row)


def _job_to_row(job: Job) -> JobRow:
    return JobRow(
        id=job.id,
        type=job.type.value,
        entity_type=job.entity_type,
        entity_id=job.entity_id,
        priority=job.priority,
        status=job.status.value,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        available_at=_iso(job.available_at),
        locked_by=job.locked_by,
        locked_at=None if job.locked_at is None else _iso(job.locked_at),
        lease_expires_at=(None if job.lease_expires_at is None else _iso(job.lease_expires_at)),
        correlation_id=job.correlation_id,
        payload=json.dumps(dict(job.payload), ensure_ascii=False, sort_keys=True),
        schema_version=job.schema_version,
        created_at=_iso(job.created_at),
        updated_at=_iso(job.updated_at),
    )


def _job_from_row(row: JobRow) -> Job:
    return Job(
        id=row.id,
        type=JobType(row.type),
        status=JobStatus(row.status),
        priority=row.priority,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        available_at=_parse(row.available_at),
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        locked_by=row.locked_by,
        locked_at=None if row.locked_at is None else _parse(row.locked_at),
        lease_expires_at=(None if row.lease_expires_at is None else _parse(row.lease_expires_at)),
        correlation_id=row.correlation_id,
        payload=json.loads(row.payload),
        created_at=_parse(row.created_at),
        updated_at=_parse(row.updated_at),
        schema_version=row.schema_version,
    )


def _lock_from_row(row: JobLockRow) -> Lock:
    return Lock(
        name=row.name,
        owner=row.owner,
        acquired_at=_parse(row.acquired_at),
        expires_at=_parse(row.expires_at),
        correlation_id=row.correlation_id,
    )


def _audit_row(
    *,
    job_id: str,
    event_type: str,
    correlation_id: str,
    recorded_at: datetime,
    payload: dict[str, Any],
    id_factory: IdFactory,
    entity_type: str = ENTITY_JOB,
) -> AuditEventRow:
    return AuditEventRow(
        id=id_factory("aud"),
        event_type=event_type,
        entity_type=entity_type,
        entity_id=job_id,
        source=AUDIT_SOURCE_JOB,
        correlation_id=correlation_id,
        payload=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        recorded_at=_iso(recorded_at),
    )


__all__ = [
    "SqlAlchemyJobRepository",
]
