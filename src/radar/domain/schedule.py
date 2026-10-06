"""Persistent Scheduler definitions, cadence and coalescing (RDR-039).

The Scheduler of ``docs/08_WORKFLOW_ENGINE.md`` supports ``INTERVAL``, ``CRON`` and
``ON_DEMAND`` schedules and **only creates Jobs** -- it never executes business
logic (AUT-117). This module is framework-free (no FastAPI/SQLAlchemy/Chrome): it
validates a schedule, decides whether a tick must enqueue a Job, coalesces
missed ticks into a single Job (AUT-134, AUT-343) and evaluates the configured
quiet windows in the schedule timezone (AUT-143).

A tick that would overlap an equivalent execution is skipped while the
equivalent logical lock is active, so a schedule never creates overlapping work
(AUT-140). The scheduler consults the lock; the executor (worker) owns it, and
wiring the worker to renew/release it belongs to a dependent ticket.

Persistence lives in infrastructure; every decision is auditable and observable
from the public boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from radar.domain.capture import IdFactory, default_id_factory, sanitize_single_line
from radar.domain.errors import RadarError, RadarException
from radar.domain.job import (
    DEFAULT_MAX_ATTEMPTS,
    Job,
    JobError,
    JobType,
    create_job,
    validate_job_payload,
)

#: Version of the public Schedule contract (``docs/04_DATA_CONTRACTS.md``).
SCHEDULE_SCHEMA_VERSION = "1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
SCHEDULE_INPUT_INVALID = "RAD-WF-012"
SCHEDULE_NOT_FOUND = "RAD-WF-013"

#: Operational timezone target of ``docs/10_PERSISTENCE_AND_RECOVERY.md``.
DEFAULT_SCHEDULE_TIMEZONE = "America/Maceio"

#: Hard cap on the reported coalesced occurrences, so a very old cursor can never
#: produce an unbounded audit payload (the Job itself is always a single row).
MAX_COALESCED_TICKS = 10_000

#: Provenance source recorded on scheduler audit events.
AUDIT_SOURCE_SCHEDULER = "scheduler"

#: Entity type recorded on scheduler audit events.
ENTITY_SCHEDULE = "schedule"


class ScheduleType(StrEnum):
    """Cadences supported by the Scheduler (SDD-08)."""

    INTERVAL = "INTERVAL"
    CRON = "CRON"
    ON_DEMAND = "ON_DEMAND"


class TickAction(StrEnum):
    """Outcome of evaluating one schedule at a point in time."""

    ENQUEUE = "ENQUEUE"
    SKIP_LOCKED = "SKIP_LOCKED"
    SKIP_QUIET_WINDOW = "SKIP_QUIET_WINDOW"
    SKIP_NOT_DUE = "SKIP_NOT_DUE"
    SKIP_DISABLED = "SKIP_DISABLED"


class ScheduleError(RadarException):
    """Base error raised when a Schedule operation cannot be completed."""


def schedule_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> ScheduleError:
    """Build the structured error for an invalid Schedule input."""

    return ScheduleError(
        RadarError(
            code=SCHEDULE_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir a definição do schedule e enviar novamente",
            context=dict(context or {}),
        )
    )


def schedule_not_found_error(schedule_id: str) -> ScheduleError:
    """Build the structured not-found error for a Schedule query."""

    return ScheduleError(
        RadarError(
            code=SCHEDULE_NOT_FOUND,
            message="Schedule não encontrado",
            retryable=False,
            action="Verificar o schedule_id informado",
            context={"schedule_id": schedule_id},
        )
    )


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _input_invalid(message: str, *, field: str) -> ScheduleError:
    return schedule_input_invalid_error(message, context={"field": field})


def _require_clean_token(value: object, *, field_name: str, max_length: int = 128) -> str:
    if not isinstance(value, str):
        raise _input_invalid("valor deve ser texto", field=field_name)
    cleaned = sanitize_single_line(value)
    if not cleaned:
        raise _input_invalid("valor não pode ser vazio", field=field_name)
    if len(cleaned) > max_length:
        raise _input_invalid("valor excede o tamanho máximo", field=field_name)
    return cleaned


def _parse_hhmm(value: object, *, field_name: str) -> int:
    if not isinstance(value, str):
        raise _input_invalid("horário deve ser texto HH:MM", field=field_name)
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise _input_invalid("horário deve seguir HH:MM", field=field_name)
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise _input_invalid("horário deve seguir HH:MM", field=field_name) from exc
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        raise _input_invalid("horário fora de 00:00..23:59", field=field_name)
    return hour * 60 + minute


@dataclass(frozen=True, slots=True)
class QuietWindow:
    """A recurring local-time window in which a schedule must not enqueue.

    ``start``/``end`` are ``HH:MM`` local times in the schedule timezone. A window
    whose ``end`` is not after ``start`` wraps past midnight. ``days`` is the set
    of start weekdays (0 = Monday, matching ``datetime.weekday``); an empty set
    means every day.
    """

    start: str
    end: str
    days: tuple[int, ...] = ()

    def to_contract(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "days": list(self.days)}

    def contains(self, local_moment: datetime) -> bool:
        """True when ``local_moment`` (schedule timezone) falls in this window."""

        start = _parse_hhmm(self.start, field_name="quiet_window.start")
        end = _parse_hhmm(self.end, field_name="quiet_window.end")
        minutes = local_moment.hour * 60 + local_moment.minute
        weekday = local_moment.weekday()
        if start < end:
            effective_day = weekday
            inside = start <= minutes < end
        else:
            # Wraps midnight: the post-midnight part belongs to the previous day.
            effective_day = (weekday - 1) % 7 if minutes < end else weekday
            inside = minutes >= start or minutes < end
        if not inside:
            return False
        return not self.days or effective_day in self.days


def _parse_days(value: object) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _input_invalid("days deve ser uma lista de inteiros 0..6", field="days")
    days: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not (0 <= item <= 6):
            raise _input_invalid("days deve ser uma lista de inteiros 0..6", field="days")
        if item not in days:
            days.append(item)
    return tuple(sorted(days))


def _coerce_quiet_window(value: object) -> QuietWindow:
    if isinstance(value, QuietWindow):
        return value
    if not isinstance(value, Mapping):
        raise _input_invalid("quiet_window deve ser um objeto", field="quiet_windows")
    start = _require_clean_token(value.get("start"), field_name="quiet_window.start", max_length=5)
    end = _require_clean_token(value.get("end"), field_name="quiet_window.end", max_length=5)
    start_minutes = _parse_hhmm(start, field_name="quiet_window.start")
    end_minutes = _parse_hhmm(end, field_name="quiet_window.end")
    if start_minutes == end_minutes:
        raise _input_invalid("quiet_window.start e end não podem ser iguais", field="quiet_windows")
    return QuietWindow(start=start, end=end, days=_parse_days(value.get("days")))


def _parse_quiet_windows(value: object) -> tuple[QuietWindow, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _input_invalid("quiet_windows deve ser uma lista", field="quiet_windows")
    return tuple(_coerce_quiet_window(item) for item in value)


def _coerce_schedule_type(value: object) -> ScheduleType:
    if isinstance(value, ScheduleType):
        return value
    try:
        return ScheduleType(str(value))
    except ValueError as exc:
        raise _input_invalid(
            "type de schedule inválido",
            field="type",
        ) from exc


def _coerce_job_type(value: object) -> JobType:
    if isinstance(value, JobType):
        return value
    try:
        return JobType(str(value))
    except ValueError as exc:
        raise _input_invalid(
            "job_type inválido",
            field="job_type",
        ) from exc


def _validate_timezone(value: object) -> str:
    if value is None:
        return DEFAULT_SCHEDULE_TIMEZONE
    if not isinstance(value, str):
        raise _input_invalid("timezone deve ser texto IANA", field="timezone")
    cleaned = value.strip()
    try:
        ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise _input_invalid("timezone IANA inválida", field="timezone") from exc
    return cleaned


# -- Minimal cron support ---------------------------------------------------


def _parse_cron_field(
    field: str,
    minimum: int,
    maximum: int,
    *,
    normalize: Any = None,
) -> frozenset[int]:
    values: set[int] = set()
    for raw_part in field.split(","):
        part = raw_part.strip()
        if not part:
            raise _input_invalid("campo de cron vazio", field="cron")
        step = 1
        if "/" in part:
            base, _, step_text = part.partition("/")
            try:
                step = int(step_text)
            except ValueError as exc:
                raise _input_invalid("passo de cron inválido", field="cron") from exc
            if step <= 0:
                raise _input_invalid("passo de cron deve ser positivo", field="cron")
        else:
            base = part
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            low, _, high = base.partition("-")
            try:
                start, end = int(low), int(high)
            except ValueError as exc:
                raise _input_invalid("intervalo de cron inválido", field="cron") from exc
            if start > end:
                raise _input_invalid("intervalo de cron invertido", field="cron")
        else:
            try:
                start = end = int(base)
            except ValueError as exc:
                raise _input_invalid("valor de cron inválido", field="cron") from exc
        for value in range(start, end + 1, step):
            if value < minimum or value > maximum:
                raise _input_invalid("valor de cron fora da faixa", field="cron")
            values.add(normalize(value) if normalize is not None else value)
    if not values:
        raise _input_invalid("campo de cron sem valores", field="cron")
    return frozenset(values)


@dataclass(frozen=True, slots=True)
class CronExpression:
    """A standard five-field cron expression (minute hour dom month dow).

    Supports ``*``, single values, ranges ``a-b``, lists ``a,b`` and steps
    ``*/n`` / ``a-b/n``. Day-of-week accepts ``0`` or ``7`` as Sunday.
    """

    minute: frozenset[int]
    hour: frozenset[int]
    day_of_month: frozenset[int]
    month: frozenset[int]
    day_of_week: frozenset[int]
    raw: str

    @classmethod
    def parse(cls, value: object) -> CronExpression:
        if not isinstance(value, str):
            raise _input_invalid("cron deve ser texto", field="cron")
        fields = value.split()
        if len(fields) != 5:
            raise _input_invalid("cron deve ter 5 campos", field="cron")
        return cls(
            minute=_parse_cron_field(fields[0], 0, 59),
            hour=_parse_cron_field(fields[1], 0, 23),
            day_of_month=_parse_cron_field(fields[2], 1, 31),
            month=_parse_cron_field(fields[3], 1, 12),
            day_of_week=_parse_cron_field(fields[4], 0, 7, normalize=lambda v: 0 if v == 7 else v),
            raw=value.strip(),
        )

    def _day_matches(self, moment: datetime) -> bool:
        dom_all = self.day_of_month == frozenset(range(1, 32))
        dow_all = self.day_of_week == frozenset(range(0, 7))
        dom_match = moment.day in self.day_of_month
        dow_match = ((moment.weekday() + 1) % 7) in self.day_of_week
        if dom_all or dow_all:
            return dom_match and dow_match
        return dom_match or dow_match

    def next_after(self, after: datetime) -> datetime | None:
        """Return the first matching local moment strictly after ``after``."""

        candidate = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
        limit = candidate + timedelta(days=366 * 5)
        while candidate <= limit:
            if candidate.month not in self.month:
                year = candidate.year + (1 if candidate.month == 12 else 0)
                month = 1 if candidate.month == 12 else candidate.month + 1
                candidate = candidate.replace(year=year, month=month, day=1, hour=0, minute=0)
                continue
            if not self._day_matches(candidate):
                candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if candidate.hour not in self.hour:
                candidate = (candidate + timedelta(hours=1)).replace(minute=0)
                continue
            if candidate.minute not in self.minute:
                candidate = candidate + timedelta(minutes=1)
                continue
            return candidate
        return None


# -- Schedule model ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Schedule:
    """A durable schedule that creates Jobs (RDR-039, AUT-117)."""

    id: str
    name: str
    type: ScheduleType
    job_type: JobType
    priority: int
    max_attempts: int
    enabled: bool
    timezone: str
    lock_name: str
    payload: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime
    interval_seconds: int | None = None
    cron: str | None = None
    quiet_windows: tuple[QuietWindow, ...] = ()
    entity_type: str | None = None
    entity_id: str | None = None
    last_tick_at: datetime | None = None
    schema_version: str = SCHEDULE_SCHEMA_VERSION

    def local(self, moment: datetime) -> datetime:
        """Convert an instant to this schedule's operational timezone."""

        return _to_utc(moment).astimezone(ZoneInfo(self.timezone))

    def to_contract(self) -> dict[str, Any]:
        """Return the versioned public contract for this schedule."""

        next_run = next_run_at(self)
        return {
            "schema_version": self.schema_version,
            "schedule_id": self.id,
            "name": self.name,
            "type": self.type.value,
            "job_type": self.job_type.value,
            "priority": self.priority,
            "max_attempts": self.max_attempts,
            "enabled": self.enabled,
            "timezone": self.timezone,
            "interval_seconds": self.interval_seconds,
            "cron": self.cron,
            "quiet_windows": [window.to_contract() for window in self.quiet_windows],
            "lock_name": self.lock_name,
            "payload": dict(self.payload),
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "last_tick_at": (
                None if self.last_tick_at is None else _to_utc(self.last_tick_at).isoformat()
            ),
            "next_run_at": None if next_run is None else _to_utc(next_run).isoformat(),
            "created_at": _to_utc(self.created_at).isoformat(),
            "updated_at": _to_utc(self.updated_at).isoformat(),
        }


@dataclass(frozen=True, slots=True)
class TickPlan:
    """Deterministic decision for evaluating one schedule at one instant."""

    action: TickAction
    occurrence_count: int
    scheduled_for: datetime | None
    reason: str
    lock_name: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "occurrence_count": self.occurrence_count,
            "scheduled_for": (
                None if self.scheduled_for is None else _to_utc(self.scheduled_for).isoformat()
            ),
            "lock_name": self.lock_name,
        }


@dataclass(frozen=True, slots=True)
class TickResult:
    """Persisted outcome of one tick, observable from the public boundary."""

    schedule: Schedule
    plan: TickPlan
    job: Job | None
    correlation_id: str
    now: datetime

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEDULE_SCHEMA_VERSION,
            "schedule_id": self.schedule.id,
            "schedule_name": self.schedule.name,
            "action": self.plan.action.value,
            "reason": self.plan.reason,
            "occurrence_count": self.plan.occurrence_count,
            "scheduled_for": self.plan.to_contract()["scheduled_for"],
            "lock_name": self.plan.lock_name,
            "job": None if self.job is None else self.job.to_contract(),
            "correlation_id": self.correlation_id,
            "ticked_at": _to_utc(self.now).isoformat(),
        }


def build_schedule(
    *,
    name: object,
    schedule_type: object,
    job_type: object,
    now: datetime,
    priority: object = 0,
    max_attempts: object = DEFAULT_MAX_ATTEMPTS,
    enabled: object = True,
    timezone: object = None,
    interval_seconds: object = None,
    cron: object = None,
    quiet_windows: object = None,
    lock_name: object = None,
    payload: object = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    schema_version: object = SCHEDULE_SCHEMA_VERSION,
    last_tick_at: datetime | None = None,
    id_factory: IdFactory = default_id_factory,
) -> Schedule:
    """Build and validate a Schedule (RDR-039).

    The cadence fields are mutually exclusive and fail closed: an ``INTERVAL``
    requires ``interval_seconds`` and no ``cron``, a ``CRON`` requires a valid
    expression and no interval, and ``ON_DEMAND`` accepts neither. The payload is
    validated with the same rules as a Job payload, so a schedule can never
    persist a sensitive or non-JSON payload.
    """

    if str(schema_version) != SCHEDULE_SCHEMA_VERSION:
        raise schedule_input_invalid_error(
            "schema_version de schedule não suportada",
            context={"field": "schema_version", "supported": SCHEDULE_SCHEMA_VERSION},
        )
    resolved_name = _require_clean_token(name, field_name="name", max_length=128)
    resolved_type = _coerce_schedule_type(schedule_type)
    resolved_job_type = _coerce_job_type(job_type)
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise _input_invalid("priority deve ser um inteiro", field="priority")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise _input_invalid(
            "max_attempts deve ser um inteiro maior ou igual a 1", field="max_attempts"
        )
    if not isinstance(enabled, bool):
        raise _input_invalid("enabled deve ser booleano", field="enabled")
    if (entity_type is None) != (entity_id is None):
        raise _input_invalid("entity_type e entity_id devem ser informados juntos", field="entity")
    resolved_entity_type = (
        None
        if entity_type is None
        else _require_clean_token(entity_type, field_name="entity_type", max_length=32)
    )
    resolved_entity_id = (
        None
        if entity_id is None
        else _require_clean_token(entity_id, field_name="entity_id", max_length=64)
    )

    resolved_interval: int | None = None
    resolved_cron: str | None = None
    if resolved_type is ScheduleType.INTERVAL:
        if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int):
            raise _input_invalid(
                "INTERVAL exige interval_seconds inteiro", field="interval_seconds"
            )
        if interval_seconds <= 0:
            raise _input_invalid(
                "interval_seconds deve ser maior que zero", field="interval_seconds"
            )
        if cron is not None:
            raise _input_invalid("INTERVAL não aceita cron", field="cron")
        resolved_interval = interval_seconds
    elif resolved_type is ScheduleType.CRON:
        if cron is None:
            raise _input_invalid("CRON exige uma expressão cron", field="cron")
        if interval_seconds is not None:
            raise _input_invalid("CRON não aceita interval_seconds", field="interval_seconds")
        CronExpression.parse(cron)
        resolved_cron = str(cron).strip()
    else:
        if interval_seconds is not None or cron is not None:
            raise _input_invalid("ON_DEMAND não aceita interval_seconds nem cron", field="type")

    resolved_lock = (
        f"schedule:{resolved_name}"
        if lock_name is None
        else _require_clean_token(lock_name, field_name="lock_name", max_length=128)
    )
    reference = _to_utc(now)
    resolved_last_tick = reference if last_tick_at is None else _to_utc(last_tick_at)
    try:
        resolved_payload = validate_job_payload(payload)
    except JobError as exc:
        raise schedule_input_invalid_error(
            "payload de schedule inválido",
            context=dict(exc.error.context),
        ) from exc
    return Schedule(
        id=id_factory("sch"),
        name=resolved_name,
        type=resolved_type,
        job_type=resolved_job_type,
        priority=priority,
        max_attempts=max_attempts,
        enabled=enabled,
        timezone=_validate_timezone(timezone),
        lock_name=resolved_lock,
        payload=resolved_payload,
        created_at=reference,
        updated_at=reference,
        interval_seconds=resolved_interval,
        cron=resolved_cron,
        quiet_windows=_parse_quiet_windows(quiet_windows),
        entity_type=resolved_entity_type,
        entity_id=resolved_entity_id,
        last_tick_at=resolved_last_tick,
    )


def next_run_at(schedule: Schedule) -> datetime | None:
    """Return the next cadence occurrence after the schedule cursor, in UTC."""

    if schedule.last_tick_at is None:
        return None
    if schedule.type is ScheduleType.INTERVAL:
        assert schedule.interval_seconds is not None
        return _to_utc(schedule.last_tick_at) + timedelta(seconds=schedule.interval_seconds)
    if schedule.type is ScheduleType.CRON:
        assert schedule.cron is not None
        local_cursor = schedule.local(schedule.last_tick_at)
        following = CronExpression.parse(schedule.cron).next_after(local_cursor)
        return None if following is None else _to_utc(following)
    return None


def occurrence_count(schedule: Schedule, now: datetime) -> int:
    """Count cadence occurrences due since the schedule cursor (capped).

    ``ON_DEMAND`` has no cadence and always yields ``0``. A cadence schedule
    yields the number of missed ticks, so the caller can coalesce them into a
    single Job instead of replaying every tick (AUT-134).
    """

    reference = _to_utc(now)
    if schedule.type is ScheduleType.ON_DEMAND or schedule.last_tick_at is None:
        return 0
    cursor = _to_utc(schedule.last_tick_at)
    if schedule.type is ScheduleType.INTERVAL:
        assert schedule.interval_seconds is not None
        elapsed = (reference - cursor).total_seconds()
        if elapsed < schedule.interval_seconds:
            return 0
        return min(MAX_COALESCED_TICKS, max(0, int(elapsed // schedule.interval_seconds)))
    assert schedule.cron is not None
    expression = CronExpression.parse(schedule.cron)
    count = 0
    while count < MAX_COALESCED_TICKS:
        following = expression.next_after(schedule.local(cursor))
        if following is None:
            break
        following_utc = _to_utc(following)
        if following_utc > reference:
            break
        count += 1
        cursor = following_utc
    return count


def is_quiet(schedule: Schedule, now: datetime) -> bool:
    """True when ``now`` falls in one of the schedule's quiet windows."""

    if not schedule.quiet_windows:
        return False
    local = schedule.local(now)
    return any(window.contains(local) for window in schedule.quiet_windows)


def plan_tick(
    schedule: Schedule,
    *,
    now: datetime,
    lock_active: bool,
    forced: bool = False,
) -> TickPlan:
    """Decide whether one schedule must enqueue a Job at ``now``.

    A disabled schedule never enqueues. An active equivalent lock or a quiet
    window defers the tick without advancing the cursor, so the deferred ticks
    coalesce into the next allowed Job. Otherwise the tick enqueues exactly one
    Job for every due occurrence.
    """

    reference = _to_utc(now)
    if not schedule.enabled:
        return TickPlan(TickAction.SKIP_DISABLED, 0, None, "DISABLED", schedule.lock_name)
    pending = occurrence_count(schedule, reference)
    if lock_active:
        deferred = pending if pending > 0 else (1 if forced else 0)
        return TickPlan(
            TickAction.SKIP_LOCKED, deferred, None, "EQUIVALENT_LOCK_HELD", schedule.lock_name
        )
    if is_quiet(schedule, reference):
        deferred = pending if pending > 0 else (1 if forced else 0)
        return TickPlan(
            TickAction.SKIP_QUIET_WINDOW, deferred, None, "QUIET_WINDOW", schedule.lock_name
        )
    if forced:
        count = max(1, pending)
        reason = (
            "FORCED"
            if schedule.type is ScheduleType.ON_DEMAND
            else ("COALESCED" if count > 1 else "DUE")
        )
        return TickPlan(TickAction.ENQUEUE, count, reference, reason, schedule.lock_name)
    if pending <= 0:
        return TickPlan(TickAction.SKIP_NOT_DUE, 0, None, "NOT_DUE", schedule.lock_name)
    return TickPlan(
        TickAction.ENQUEUE,
        pending,
        reference,
        "COALESCED" if pending > 1 else "DUE",
        schedule.lock_name,
    )


def apply_tick(schedule: Schedule, plan: TickPlan, *, now: datetime) -> Schedule:
    """Return the schedule after a tick: the cursor only advances on enqueue."""

    if plan.action is not TickAction.ENQUEUE:
        return schedule
    reference = _to_utc(now)
    return replace(schedule, last_tick_at=reference, updated_at=reference)


def set_enabled(schedule: Schedule, *, enabled: object, now: datetime) -> Schedule:
    """Return the schedule with its enabled flag updated (idempotent)."""

    if not isinstance(enabled, bool):
        raise _input_invalid("enabled deve ser booleano", field="enabled")
    if schedule.enabled is enabled:
        return schedule
    return replace(schedule, enabled=enabled, updated_at=_to_utc(now))


def build_scheduled_job(
    schedule: Schedule,
    plan: TickPlan,
    *,
    correlation_id: str,
    now: datetime,
    id_factory: IdFactory = default_id_factory,
) -> Job:
    """Build the single coalesced Job for a tick (the Scheduler never runs it)."""

    payload = {
        **dict(schedule.payload),
        "schedule_id": schedule.id,
        "schedule_name": schedule.name,
        "scheduled_occurrences": plan.occurrence_count,
    }
    return create_job(
        job_type=schedule.job_type,
        correlation_id=correlation_id,
        now=now,
        payload=payload,
        priority=schedule.priority,
        entity_type=schedule.entity_type,
        entity_id=schedule.entity_id,
        available_at=now,
        max_attempts=schedule.max_attempts,
        id_factory=id_factory,
    )


__all__ = [
    "AUDIT_SOURCE_SCHEDULER",
    "DEFAULT_SCHEDULE_TIMEZONE",
    "ENTITY_SCHEDULE",
    "MAX_COALESCED_TICKS",
    "SCHEDULE_INPUT_INVALID",
    "SCHEDULE_NOT_FOUND",
    "SCHEDULE_SCHEMA_VERSION",
    "CronExpression",
    "QuietWindow",
    "Schedule",
    "ScheduleError",
    "ScheduleType",
    "TickAction",
    "TickPlan",
    "TickResult",
    "apply_tick",
    "build_schedule",
    "build_scheduled_job",
    "is_quiet",
    "next_run_at",
    "occurrence_count",
    "plan_tick",
    "schedule_input_invalid_error",
    "schedule_not_found_error",
    "set_enabled",
]
