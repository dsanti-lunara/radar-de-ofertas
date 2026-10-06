"""Scheduler orchestration: create schedules and turn ticks into Jobs (RDR-039).

The Scheduler validates the public inputs and delegates the atomic
``tick -> Job + cursor + audit`` write to a :class:`ScheduleStore` port. It never
executes business logic (AUT-117): a tick can only create a ``PENDING`` Job, and
the equivalent logical lock defers a tick while an equivalent execution is in
progress. Missed ticks are coalesced into a single Job (AUT-134).

The domain stays framework-free; the SQLAlchemy implementation lives in
infrastructure (AUT-397).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.job import Job, Lock
from radar.domain.schedule import (
    SCHEDULE_SCHEMA_VERSION,
    Schedule,
    TickAction,
    TickPlan,
    TickResult,
    build_schedule,
    build_scheduled_job,
    plan_tick,
    schedule_not_found_error,
    set_enabled,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ScheduleStore(Protocol):
    """Persistence port for schedules and the atomic tick write."""

    def create(self, schedule: Schedule, *, correlation_id: str | None = None) -> Schedule: ...

    def get(self, schedule_id: str) -> Schedule | None: ...

    def get_by_name(self, name: str) -> Schedule | None: ...

    def list(self) -> list[Schedule]: ...

    def save(self, schedule: Schedule, *, correlation_id: str | None = None) -> Schedule: ...

    def get_lock(self, name: str) -> Lock | None: ...

    def apply_tick(
        self,
        schedule: Schedule,
        *,
        plan: TickPlan,
        now: datetime,
        correlation_id: str,
        job: Job | None,
    ) -> tuple[Schedule, bool]: ...


@dataclass(slots=True)
class ScheduleService:
    """Validate and drive schedules through the public boundary."""

    repository: ScheduleStore
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory

    def create(
        self,
        *,
        name: object,
        schedule_type: object,
        job_type: object,
        priority: object = 0,
        max_attempts: object = None,
        enabled: object = True,
        timezone: object = None,
        interval_seconds: object = None,
        cron: object = None,
        quiet_windows: object = None,
        lock_name: object = None,
        payload: Mapping[str, Any] | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        schema_version: object = SCHEDULE_SCHEMA_VERSION,
        correlation_id: str | None = None,
    ) -> Schedule:
        """Build and persist a schedule (RDR-039)."""

        now = self.clock()
        kwargs: dict[str, Any] = {
            "name": name,
            "schedule_type": schedule_type,
            "job_type": job_type,
            "now": now,
            "priority": priority,
            "enabled": enabled,
            "timezone": timezone,
            "interval_seconds": interval_seconds,
            "cron": cron,
            "quiet_windows": quiet_windows,
            "lock_name": lock_name,
            "payload": payload,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "schema_version": schema_version,
            "id_factory": self.id_factory,
        }
        if max_attempts is not None:
            kwargs["max_attempts"] = max_attempts
        schedule = build_schedule(**kwargs)
        return self.repository.create(schedule, correlation_id=correlation_id)

    def get(self, schedule_id: str) -> Schedule:
        """Return a persisted schedule, raising a structured not-found error."""

        schedule = self.repository.get(schedule_id)
        if schedule is None:
            raise schedule_not_found_error(schedule_id)
        return schedule

    def get_by_name(self, name: str) -> Schedule:
        """Return a persisted schedule by name, raising when absent."""

        schedule = self.repository.get_by_name(name)
        if schedule is None:
            raise schedule_not_found_error(name)
        return schedule

    def list(self) -> list[Schedule]:
        """Return every persisted schedule, oldest first."""

        return self.repository.list()

    def set_enabled(
        self, schedule_id: str, *, enabled: object, correlation_id: str | None = None
    ) -> Schedule:
        """Enable or disable a schedule (idempotent)."""

        schedule = self.get(schedule_id)
        updated = set_enabled(schedule, enabled=enabled, now=self.clock())
        if updated is schedule:
            return schedule
        return self.repository.save(updated, correlation_id=correlation_id)

    def tick_schedule(
        self,
        schedule_id: str,
        *,
        correlation_id: str,
        now: datetime | None = None,
        forced: bool = True,
    ) -> TickResult:
        """Evaluate one schedule and persist its coalesced Job when due."""

        return self._tick(
            self.get(schedule_id),
            correlation_id=correlation_id,
            now=self.clock() if now is None else now,
            forced=forced,
        )

    def tick_due(self, *, correlation_id: str, now: datetime | None = None) -> list[TickResult]:
        """Evaluate every enabled schedule that has a cadence due now."""

        reference = self.clock() if now is None else now
        results: list[TickResult] = []
        for schedule in self.repository.list():
            if not schedule.enabled:
                continue
            results.append(
                self._tick(schedule, correlation_id=correlation_id, now=reference, forced=False)
            )
        return results

    def _tick(
        self,
        schedule: Schedule,
        *,
        correlation_id: str,
        now: datetime,
        forced: bool,
    ) -> TickResult:
        lock = self.repository.get_lock(schedule.lock_name)
        lock_active = lock is not None and lock.is_active(now)
        plan = plan_tick(schedule, now=now, lock_active=lock_active, forced=forced)
        job: Job | None = None
        if plan.action is TickAction.ENQUEUE:
            job = build_scheduled_job(
                schedule,
                plan,
                correlation_id=correlation_id,
                now=now,
                id_factory=self.id_factory,
            )
        updated, applied = self.repository.apply_tick(
            schedule,
            plan=plan,
            now=now,
            correlation_id=correlation_id,
            job=job,
        )
        if not applied:
            # Another tick advanced the cursor first; this one is a no-op so the
            # Scheduler never creates an overlapping Job.
            plan = replace(
                plan,
                action=TickAction.SKIP_NOT_DUE,
                reason="TICK_ALREADY_APPLIED",
                occurrence_count=0,
                scheduled_for=None,
            )
            job = None
        return TickResult(
            schedule=updated,
            plan=plan,
            job=job,
            correlation_id=correlation_id,
            now=now,
        )


__all__ = [
    "ScheduleService",
    "ScheduleStore",
]
