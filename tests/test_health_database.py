from __future__ import annotations

import pytest

from radar.bootstrap import build_health_service
from radar.domain.health import HealthCheck, HealthState, SystemHealth
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.integration


def _report(database_url: str) -> SystemHealth:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    try:
        return build_health_service(settings, engine).evaluate()
    finally:
        engine.dispose()


def _checks_by_name(report: SystemHealth) -> dict[str, HealthCheck]:
    return {check.name: check for check in report.checks}


def test_migrated_database_is_healthy(migrated_database_url: str) -> None:
    report = _report(migrated_database_url)
    assert report.status is HealthState.HEALTHY
    assert report.is_operational is True
    checks = _checks_by_name(report)
    assert set(checks) == {"database", "schema"}
    assert checks["database"].state is HealthState.HEALTHY
    assert checks["schema"].state is HealthState.HEALTHY


def test_unavailable_database_is_unhealthy(unavailable_database_url: str) -> None:
    report = _report(unavailable_database_url)
    assert report.status is HealthState.UNHEALTHY
    error = _checks_by_name(report)["database"].error
    assert error is not None
    assert error.code == "RAD-DB-003"
    assert error.retryable is True


def test_migration_pending_blocks_health(database_url: str) -> None:
    report = _report(database_url)
    assert report.status is HealthState.UNHEALTHY
    error = _checks_by_name(report)["schema"].error
    assert error is not None
    assert error.code == "RAD-DB-002"
    assert error.retryable is False
