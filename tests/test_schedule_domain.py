from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from radar.domain.schedule import (
    SCHEDULE_INPUT_INVALID,
    SCHEDULE_SCHEMA_VERSION,
    CronExpression,
    QuietWindow,
    ScheduleError,
    ScheduleType,
    TickAction,
    build_schedule,
    build_scheduled_job,
    is_quiet,
    next_run_at,
    occurrence_count,
    plan_tick,
)

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _id_factory(prefix: str) -> str:
    return f"{prefix}_test"


def _schedule(**overrides: object):
    params: dict[str, object] = {
        "name": "nightly",
        "schedule_type": ScheduleType.INTERVAL,
        "job_type": "BACKUP_DATABASE",
        "now": FIXED_NOW,
        "interval_seconds": 300,
        "id_factory": _id_factory,
    }
    params.update(overrides)
    return build_schedule(**params)  # type: ignore[arg-type]


def test_interval_schedule_persists_cadence_and_contract() -> None:
    schedule = _schedule(priority=5, max_attempts=4, payload={"scope": "full"})

    assert schedule.id == "sch_test"
    assert schedule.type is ScheduleType.INTERVAL
    assert schedule.interval_seconds == 300
    assert schedule.cron is None
    assert schedule.lock_name == "schedule:nightly"
    assert schedule.schema_version == SCHEDULE_SCHEMA_VERSION
    assert schedule.last_tick_at == FIXED_NOW

    contract = schedule.to_contract()
    assert contract["type"] == "INTERVAL"
    assert contract["job_type"] == "BACKUP_DATABASE"
    assert contract["priority"] == 5
    assert contract["max_attempts"] == 4
    assert contract["next_run_at"] == (FIXED_NOW + timedelta(seconds=300)).isoformat()


def test_interval_requires_positive_seconds_and_rejects_cron() -> None:
    for bad in (None, 0, -1, True, 1.5):
        with pytest.raises(ScheduleError) as excinfo:
            _schedule(interval_seconds=bad)
        assert excinfo.value.error.code == SCHEDULE_INPUT_INVALID
    with pytest.raises(ScheduleError):
        _schedule(cron="*/5 * * * *")


def test_cron_requires_expression_and_rejects_interval() -> None:
    schedule = _schedule(
        schedule_type=ScheduleType.CRON, interval_seconds=None, cron="*/15 * * * *"
    )
    assert schedule.type is ScheduleType.CRON
    assert schedule.cron == "*/15 * * * *"
    assert schedule.interval_seconds is None

    with pytest.raises(ScheduleError):
        _schedule(schedule_type=ScheduleType.CRON, interval_seconds=None, cron=None)
    with pytest.raises(ScheduleError):
        _schedule(
            schedule_type=ScheduleType.CRON,
            interval_seconds=60,
            cron="*/15 * * * *",
        )


def test_on_demand_rejects_cadence() -> None:
    schedule = _schedule(schedule_type=ScheduleType.ON_DEMAND, interval_seconds=None)
    assert schedule.type is ScheduleType.ON_DEMAND
    with pytest.raises(ScheduleError):
        _schedule(schedule_type=ScheduleType.ON_DEMAND, interval_seconds=60)
    with pytest.raises(ScheduleError):
        _schedule(schedule_type=ScheduleType.ON_DEMAND, interval_seconds=None, cron="* * * * *")


def test_invalid_cron_and_timezone_fail_closed() -> None:
    for bad in ("not cron", "* * * *", "60 * * * *", "* * * * 9", "*/0 * * * *"):
        with pytest.raises(ScheduleError) as excinfo:
            _schedule(schedule_type=ScheduleType.CRON, interval_seconds=None, cron=bad)
        assert excinfo.value.error.code == SCHEDULE_INPUT_INVALID

    with pytest.raises(ScheduleError) as tz:
        _schedule(timezone="Not/AZone")
    assert tz.value.error.code == SCHEDULE_INPUT_INVALID


def test_sensitive_payload_is_rejected() -> None:
    with pytest.raises(ScheduleError) as excinfo:
        _schedule(payload={"password": "x"})
    assert excinfo.value.error.code == SCHEDULE_INPUT_INVALID

    with pytest.raises(ScheduleError):
        _schedule(payload={"nested": {"token": "x"}})


def test_cron_next_after_matches_weekday_expression() -> None:
    expression = CronExpression.parse("0 9 * * 1-5")
    following = expression.next_after(datetime(2026, 10, 5, 12, 0, tzinfo=UTC))
    assert following == datetime(2026, 10, 6, 9, 0, tzinfo=UTC)

    weekend = expression.next_after(datetime(2026, 10, 10, 9, 0, tzinfo=UTC))
    assert weekend == datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def test_cron_step_and_list_fields() -> None:
    expression = CronExpression.parse("0,30 */6 * * *")
    assert expression.minute == frozenset({0, 30})
    assert expression.hour == frozenset({0, 6, 12, 18})


def test_occurrence_count_coalesces_interval_backlog() -> None:
    schedule = _schedule(interval_seconds=300)
    assert occurrence_count(schedule, FIXED_NOW) == 0
    assert occurrence_count(schedule, FIXED_NOW + timedelta(seconds=100)) == 0
    assert occurrence_count(schedule, FIXED_NOW + timedelta(seconds=300)) == 1
    assert occurrence_count(schedule, FIXED_NOW + timedelta(hours=1)) == 12


def test_occurrence_count_cron_backlog() -> None:
    schedule = _schedule(schedule_type=ScheduleType.CRON, interval_seconds=None, cron="*/5 * * * *")
    assert occurrence_count(schedule, FIXED_NOW + timedelta(minutes=35)) == 7


def test_quiet_window_wraps_midnight_in_configured_timezone() -> None:
    schedule = _schedule(
        timezone="America/Maceio",
        quiet_windows=[{"start": "22:00", "end": "07:00"}],
    )
    # 02:00 UTC == 23:00 local (inside); 12:00 UTC == 09:00 local (outside).
    assert is_quiet(schedule, datetime(2026, 10, 6, 2, 0, tzinfo=UTC)) is True
    assert is_quiet(schedule, datetime(2026, 10, 6, 12, 0, tzinfo=UTC)) is False


def test_quiet_window_respects_days() -> None:
    window = QuietWindow(start="09:00", end="17:00", days=(0,))  # Mondays only
    monday = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
    tuesday = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
    assert window.contains(monday) is True
    assert window.contains(tuesday) is False


def test_plan_tick_coalesces_missed_ticks_into_one_enqueue() -> None:
    schedule = _schedule(interval_seconds=300)
    now = FIXED_NOW + timedelta(hours=1)
    plan = plan_tick(schedule, now=now, lock_active=False)
    assert plan.action is TickAction.ENQUEUE
    assert plan.reason == "COALESCED"
    assert plan.occurrence_count == 12
    assert plan.scheduled_for == now

    job = build_scheduled_job(
        schedule, plan, correlation_id="cid-1", now=now, id_factory=_id_factory
    )
    assert job.type.value == "BACKUP_DATABASE"
    assert job.payload["scheduled_occurrences"] == 12
    assert job.payload["schedule_id"] == schedule.id


def test_plan_tick_skips_when_equivalent_lock_is_active() -> None:
    schedule = _schedule(interval_seconds=300)
    now = FIXED_NOW + timedelta(hours=1)
    plan = plan_tick(schedule, now=now, lock_active=True)
    assert plan.action is TickAction.SKIP_LOCKED
    assert plan.reason == "EQUIVALENT_LOCK_HELD"
    assert plan.occurrence_count == 12


def test_plan_tick_skips_in_quiet_window() -> None:
    schedule = _schedule(
        timezone="America/Maceio",
        quiet_windows=[{"start": "22:00", "end": "07:00"}],
    )
    now = datetime(2026, 10, 6, 2, 0, tzinfo=UTC)  # 23:00 local
    plan = plan_tick(schedule, now=now, lock_active=False)
    assert plan.action is TickAction.SKIP_QUIET_WINDOW
    assert plan.reason == "QUIET_WINDOW"


def test_plan_tick_not_due_and_disabled() -> None:
    schedule = _schedule(interval_seconds=300)
    assert plan_tick(schedule, now=FIXED_NOW + timedelta(seconds=10), lock_active=False).action is (
        TickAction.SKIP_NOT_DUE
    )
    disabled = replace(schedule, enabled=False)
    assert plan_tick(disabled, now=FIXED_NOW + timedelta(hours=1), lock_active=False).action is (
        TickAction.SKIP_DISABLED
    )


def test_on_demand_only_enqueues_when_forced() -> None:
    schedule = _schedule(schedule_type=ScheduleType.ON_DEMAND, interval_seconds=None)
    assert plan_tick(schedule, now=FIXED_NOW, lock_active=False).action is TickAction.SKIP_NOT_DUE
    forced = plan_tick(schedule, now=FIXED_NOW, lock_active=False, forced=True)
    assert forced.action is TickAction.ENQUEUE
    assert forced.reason == "FORCED"
    assert forced.occurrence_count == 1


def test_next_run_at_for_interval_and_on_demand() -> None:
    interval = _schedule(interval_seconds=600)
    assert next_run_at(interval) == FIXED_NOW + timedelta(seconds=600)
    on_demand = _schedule(schedule_type=ScheduleType.ON_DEMAND, interval_seconds=None)
    assert next_run_at(on_demand) is None
