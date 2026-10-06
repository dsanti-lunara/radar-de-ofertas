"""Recovery Manager orchestration: reconcile local work after a crash (RDR-042).

The service drives the framework-free domain of :mod:`radar.domain.recovery`
against a persistence port and the existing Scheduler. On a startup (or an
explicit run) it:

1. reads the durable shutdown marker and detects/audits an **unclean shutdown**
   (AUT-229);
2. reconciles every interrupted ``CLAIMED``/``RUNNING`` job: a safe job returns
   to ``PENDING`` and a job that may have produced an unknown external side
   effect is blocked (``DEAD``) instead of being resent (GRILL-002);
3. clears orphan logical locks (AUT-140);
4. coalesces missed schedules into a single Job per schedule through the
   Scheduler (AUT-134), without executing business logic (AUT-117);
5. records the recovery summary so the outcome is observable from the public
   boundary (AUT-010, AUT-141).

The service is framework-free (no FastAPI/SQLAlchemy/Chrome) and never publishes
or creates an affiliate link (AUT-031, AUT-164). The publisher-specific
suspension of an unknown result is integrated by TKT-24.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from radar.domain.audit import (
    CLEAN_SHUTDOWN_RECORDED,
    RECOVERY_COMPLETED,
    RECOVERY_JOB_BLOCKED,
    RECOVERY_JOB_REQUEUED,
    RECOVERY_LOCK_CLEARED,
    RECOVERY_STARTED,
    UNCLEAN_SHUTDOWN_DETECTED,
    AuditEvent,
)
from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.job import ENTITY_JOB, Job, Lock
from radar.domain.recovery import (
    AUDIT_SOURCE_RECOVERY,
    CORE_STATE_ID,
    ENTITY_RUNTIME,
    RECOVERY_SCHEMA_VERSION,
    JobRecoveryDecision,
    RecoveryAction,
    RecoveryTrigger,
    RuntimeState,
    coerce_trigger,
    plan_job_recovery,
    should_clear_lock,
)
from radar.domain.schedule import TickResult


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RecoveryStore(Protocol):
    """Persistence port for the runtime marker and interrupted work."""

    def get_runtime_state(self) -> RuntimeState | None: ...

    def save_runtime_state(
        self, state: RuntimeState, audit_events: tuple[AuditEvent, ...]
    ) -> RuntimeState: ...

    def list_interrupted_jobs(self) -> list[Job]: ...

    def requeue_job(
        self, job: Job, *, now: datetime, audit_events: tuple[AuditEvent, ...]
    ) -> Job | None: ...

    def block_job(
        self, job: Job, *, now: datetime, audit_events: tuple[AuditEvent, ...]
    ) -> Job | None: ...

    def list_locks(self) -> list[Lock]: ...

    def clear_lock(self, lock: Lock, *, audit_events: tuple[AuditEvent, ...]) -> bool: ...

    def record_audit(self, audit_events: tuple[AuditEvent, ...]) -> None: ...


class ScheduleRecoveryPort(Protocol):
    """Minimal Scheduler port used to coalesce missed schedules."""

    def tick_due(self, *, correlation_id: str, now: datetime) -> list[TickResult]: ...


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """Observable outcome of one recovery run (RDR-042)."""

    trigger: RecoveryTrigger
    unclean_shutdown: bool
    state: RuntimeState
    jobs_requeued: int
    jobs_blocked: int
    locks_cleared: int
    schedules_coalesced: int
    occurrences_coalesced: int
    correlation_id: str
    recovered_at: datetime

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "status": "RECOVERED",
            "trigger": self.trigger.value,
            "unclean_shutdown": self.unclean_shutdown,
            "state": self.state.to_contract(),
            "jobs_requeued": self.jobs_requeued,
            "jobs_blocked": self.jobs_blocked,
            "locks_cleared": self.locks_cleared,
            "schedules_coalesced": self.schedules_coalesced,
            "occurrences_coalesced": self.occurrences_coalesced,
            "correlation_id": self.correlation_id,
            "recovered_at": self.recovered_at.astimezone(UTC).isoformat(),
        }


@dataclass(slots=True)
class RecoveryService:
    """Detect unclean shutdowns and reconcile local work at startup."""

    store: RecoveryStore
    schedule_service: ScheduleRecoveryPort | None = None
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory

    def status(self) -> RuntimeState | None:
        """Return the persisted runtime state, if any."""

        return self.store.get_runtime_state()

    def run_recovery(
        self,
        *,
        correlation_id: str,
        trigger: object = None,
        now: datetime | None = None,
    ) -> RecoveryReport:
        """Detect an unclean shutdown and reconcile local work."""

        reference = self.clock() if now is None else now
        resolved_trigger = coerce_trigger(trigger)
        previous = self.store.get_runtime_state()
        unclean = previous is not None and not previous.clean_shutdown
        recovery_count = (0 if previous is None else previous.recovery_count) + 1

        state = RuntimeState(
            clean_shutdown=False,
            recovery_count=recovery_count,
            started_at=reference,
            shutdown_at=None if previous is None else previous.shutdown_at,
            last_recovery_at=reference,
            updated_at=reference,
        )
        events: list[AuditEvent] = [
            self._audit(
                event_type=RECOVERY_STARTED,
                entity_id=CORE_STATE_ID,
                correlation_id=correlation_id,
                now=reference,
                payload={
                    "trigger": resolved_trigger.value,
                    "unclean_shutdown": unclean,
                    "recovery_count": recovery_count,
                },
            )
        ]
        if unclean and previous is not None:
            events.append(
                self._audit(
                    event_type=UNCLEAN_SHUTDOWN_DETECTED,
                    entity_id=CORE_STATE_ID,
                    correlation_id=correlation_id,
                    now=reference,
                    payload={"previous_started_at": self._iso(previous.started_at)},
                )
            )
        persisted = self.store.save_runtime_state(state, tuple(events))

        jobs_requeued = 0
        jobs_blocked = 0
        for job in self.store.list_interrupted_jobs():
            decision = plan_job_recovery(job, now=reference)
            event = self._job_event(job, decision, correlation_id=correlation_id, now=reference)
            if decision.action is RecoveryAction.REQUEUE:
                if self.store.requeue_job(job, now=reference, audit_events=(event,)) is not None:
                    jobs_requeued += 1
            elif self.store.block_job(job, now=reference, audit_events=(event,)) is not None:
                jobs_blocked += 1

        locks_cleared = 0
        for lock in self.store.list_locks():
            if not should_clear_lock(lock, now=reference, unclean_shutdown=unclean):
                continue
            event = self._audit(
                event_type=RECOVERY_LOCK_CLEARED,
                entity_type="lock",
                entity_id=lock.name,
                correlation_id=correlation_id,
                now=reference,
                payload={"owner": lock.owner, "expires_at": self._iso(lock.expires_at)},
            )
            if self.store.clear_lock(lock, audit_events=(event,)):
                locks_cleared += 1

        schedules_coalesced = 0
        occurrences_coalesced = 0
        if self.schedule_service is not None:
            for result in self.schedule_service.tick_due(
                correlation_id=correlation_id, now=reference
            ):
                if result.job is None:
                    continue
                schedules_coalesced += 1
                occurrences_coalesced += result.plan.occurrence_count

        self.store.record_audit(
            (
                self._audit(
                    event_type=RECOVERY_COMPLETED,
                    entity_id=CORE_STATE_ID,
                    correlation_id=correlation_id,
                    now=reference,
                    payload={
                        "unclean_shutdown": unclean,
                        "jobs_requeued": jobs_requeued,
                        "jobs_blocked": jobs_blocked,
                        "locks_cleared": locks_cleared,
                        "schedules_coalesced": schedules_coalesced,
                        "occurrences_coalesced": occurrences_coalesced,
                    },
                ),
            )
        )
        return RecoveryReport(
            trigger=resolved_trigger,
            unclean_shutdown=unclean,
            state=persisted,
            jobs_requeued=jobs_requeued,
            jobs_blocked=jobs_blocked,
            locks_cleared=locks_cleared,
            schedules_coalesced=schedules_coalesced,
            occurrences_coalesced=occurrences_coalesced,
            correlation_id=correlation_id,
            recovered_at=reference,
        )

    def record_clean_shutdown(
        self, *, correlation_id: str, now: datetime | None = None
    ) -> RuntimeState:
        """Record the clean-shutdown marker so the next startup is not unclean."""

        reference = self.clock() if now is None else now
        previous = self.store.get_runtime_state()
        state = RuntimeState(
            clean_shutdown=True,
            recovery_count=0 if previous is None else previous.recovery_count,
            started_at=None if previous is None else previous.started_at,
            shutdown_at=reference,
            last_recovery_at=None if previous is None else previous.last_recovery_at,
            updated_at=reference,
        )
        event = self._audit(
            event_type=CLEAN_SHUTDOWN_RECORDED,
            entity_id=CORE_STATE_ID,
            correlation_id=correlation_id,
            now=reference,
            payload={"recovery_count": state.recovery_count},
        )
        return self.store.save_runtime_state(state, (event,))

    # -- internals ----------------------------------------------------------

    def _job_event(
        self,
        job: Job,
        decision: JobRecoveryDecision,
        *,
        correlation_id: str,
        now: datetime,
    ) -> AuditEvent:
        event_type = (
            RECOVERY_JOB_REQUEUED
            if decision.action is RecoveryAction.REQUEUE
            else RECOVERY_JOB_BLOCKED
        )
        return self._audit(
            event_type=event_type,
            entity_type=ENTITY_JOB,
            entity_id=job.id,
            correlation_id=correlation_id,
            now=now,
            payload={
                "type": job.type.value,
                "previous_status": job.status.value,
                "action": decision.action.value,
                "reason": decision.reason,
            },
        )

    def _audit(
        self,
        *,
        event_type: str,
        correlation_id: str,
        now: datetime,
        payload: dict[str, Any],
        entity_type: str = ENTITY_RUNTIME,
        entity_id: str = CORE_STATE_ID,
    ) -> AuditEvent:
        return AuditEvent(
            id=str(self.id_factory("aud")),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            source=AUDIT_SOURCE_RECOVERY,
            correlation_id=correlation_id,
            recorded_at=now,
            payload=payload,
        )

    @staticmethod
    def _iso(moment: datetime | None) -> str | None:
        return None if moment is None else moment.astimezone(UTC).isoformat()


__all__ = [
    "RecoveryReport",
    "RecoveryService",
    "RecoveryStore",
    "ScheduleRecoveryPort",
]
