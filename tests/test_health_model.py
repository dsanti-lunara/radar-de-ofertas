from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from radar.application.health_service import HealthService
from radar.domain.health import (
    HEALTH_PROBE_FAILED,
    HealthCheck,
    HealthState,
    SystemHealth,
    aggregate_health,
)

pytestmark = pytest.mark.unit

FIXED_TIME = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


class _Probe:
    def __init__(self, name: str, check: Callable[[], HealthCheck]) -> None:
        self._name = name
        self._check = check

    @property
    def name(self) -> str:
        return self._name

    def check(self) -> HealthCheck:
        return self._check()


def _healthy(name: str) -> HealthCheck:
    return HealthCheck(name=name, state=HealthState.HEALTHY, summary="ok")


def _service(
    *checks: HealthCheck,
    clock: Callable[[], datetime] | None = None,
    correlation_id_factory: Callable[[], str] | None = None,
) -> HealthService:
    probes = [
        _Probe(f"probe-{index}", lambda check=check: check) for index, check in enumerate(checks)
    ]
    return HealthService(
        probes,
        app_version="0.0.0-test",
        clock=clock or (lambda: FIXED_TIME),
        correlation_id_factory=correlation_id_factory or (lambda: "cid-fixed"),
    )


def test_empty_checks_is_unknown() -> None:
    assert aggregate_health([]) is HealthState.UNKNOWN


def test_unhealthy_wins_over_degraded() -> None:
    checks = [
        HealthCheck(name="a", state=HealthState.DEGRADED, summary="d"),
        HealthCheck(name="b", state=HealthState.UNHEALTHY, summary="u"),
    ]
    assert aggregate_health(checks) is HealthState.UNHEALTHY


def test_unknown_is_reported_as_degraded() -> None:
    checks = [HealthCheck(name="a", state=HealthState.UNKNOWN, summary="?")]
    assert aggregate_health(checks) is HealthState.DEGRADED


def test_healthy_report_contract() -> None:
    service = _service(_healthy("database"), _healthy("schema"))
    report = service.evaluate()
    assert isinstance(report, SystemHealth)
    assert report.status is HealthState.HEALTHY
    assert report.is_operational is True
    contract = report.to_contract()
    assert contract["schema_version"] == "1.0"
    assert contract["correlation_id"] == "cid-fixed"
    assert contract["observed_at"] == FIXED_TIME.isoformat()
    assert contract["app_version"] == "0.0.0-test"
    assert [check["name"] for check in contract["checks"]] == ["database", "schema"]


def test_correlation_id_is_echoed() -> None:
    report = _service(_healthy("database")).evaluate(correlation_id="caller-correlation")
    assert report.correlation_id == "caller-correlation"


def test_probe_exception_fails_closed() -> None:
    def boom() -> HealthCheck:
        raise RuntimeError("kaboom")

    service = HealthService(
        [_Probe("database", boom)],
        app_version="0.0.0-test",
        clock=lambda: FIXED_TIME,
        correlation_id_factory=lambda: "cid",
    )
    report = service.evaluate()
    assert report.status is HealthState.UNHEALTHY
    error = report.checks[0].error
    assert error is not None
    assert error.code == HEALTH_PROBE_FAILED
    assert error.retryable is False
    assert error.action
