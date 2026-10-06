from __future__ import annotations

from datetime import UTC, datetime

import pytest

from radar.domain.errors import RadarError
from radar.domain.health import HealthCheck, HealthState, SystemHealth
from radar.domain.home_health import (
    HOME_HEALTH_CAPABILITIES,
    REASON_INTEGRATION_HEALTH_UNAVAILABLE,
    REASON_INTEGRATION_NOT_REGISTERED,
    REASON_PROBE_NOT_REPORTED,
    SOURCE_API,
    SOURCE_HEALTH,
    SOURCE_INTEGRATION,
    SOURCE_UNREGISTERED,
    CapabilityHealth,
    HomeHealth,
    build_home_health,
)
from radar.domain.operations import IntegrationHealth, IntegrationState

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _report(
    *checks: HealthCheck,
    status: HealthState | None = None,
) -> SystemHealth:
    resolved = status or (
        HealthState.HEALTHY
        if all(check.state is HealthState.HEALTHY for check in checks)
        else HealthState.UNHEALTHY
    )
    return SystemHealth(
        schema_version="1.0",
        status=resolved,
        checks=tuple(checks),
        correlation_id="cid-home",
        observed_at=NOW,
        app_version="0.0.0-test",
    )


def _healthy(name: str) -> HealthCheck:
    return HealthCheck(name=name, state=HealthState.HEALTHY, summary=f"{name} ok")


def _integration(name: str, state: IntegrationState) -> IntegrationHealth:
    return IntegrationHealth(
        name=name, state=state, summary=f"{name} {state.value}", updated_at=NOW
    )


def _item(overview: HomeHealth, capability: str) -> CapabilityHealth:
    return next(item for item in overview.items if item.capability == capability)


def test_unregistered_dependencies_are_unknown_and_never_healthy() -> None:
    overview = build_home_health(
        report=_report(_healthy("database")),
        integrations={},
    )

    assert [item.capability for item in overview.items] == list(HOME_HEALTH_CAPABILITIES)
    assert overview.status is HealthState.DEGRADED  # unproven dependencies are not healthy
    for capability in HOME_HEALTH_CAPABILITIES:
        if capability in {"core", "database"}:
            continue
        item = _item(overview, capability)
        assert item.state is HealthState.UNKNOWN, capability
        assert item.source == SOURCE_UNREGISTERED
        assert item.reason_code == REASON_INTEGRATION_NOT_REGISTERED


def test_core_and_database_come_from_the_health_boundary() -> None:
    overview = build_home_health(
        report=_report(
            _healthy("database"),
            HealthCheck(name="schema", state=HealthState.HEALTHY, summary="schema ok"),
        ),
        integrations={},
    )

    core = _item(overview, "core")
    assert core.state is HealthState.HEALTHY
    assert core.source == SOURCE_API

    database = _item(overview, "database")
    assert database.state is HealthState.HEALTHY
    assert database.source == SOURCE_HEALTH


def test_missing_database_probe_is_unknown() -> None:
    overview = build_home_health(report=_report(), integrations={})
    database = _item(overview, "database")
    assert database.state is HealthState.UNKNOWN
    assert database.reason_code == REASON_PROBE_NOT_REPORTED


@pytest.mark.parametrize(
    ("integration_state", "expected"),
    [
        (IntegrationState.ONLINE, HealthState.HEALTHY),
        (IntegrationState.DEGRADED, HealthState.DEGRADED),
        (IntegrationState.OFFLINE, HealthState.UNHEALTHY),
        (IntegrationState.AUTH_REQUIRED, HealthState.UNHEALTHY),
        (IntegrationState.PAUSED, HealthState.UNHEALTHY),
        (IntegrationState.DISABLED, HealthState.UNHEALTHY),
        (IntegrationState.UNKNOWN, HealthState.UNKNOWN),
    ],
)
def test_registered_integration_states_map_to_capability_states(
    integration_state: IntegrationState, expected: HealthState
) -> None:
    overview = build_home_health(
        report=_report(_healthy("database")),
        integrations={"telegram": _integration("telegram", integration_state)},
    )
    telegram = _item(overview, "telegram")
    assert telegram.state is expected
    assert telegram.source == SOURCE_INTEGRATION
    assert telegram.integration == "telegram"
    assert telegram.integration_state is integration_state


def test_unreadable_integration_store_reports_health_unavailable() -> None:
    overview = build_home_health(
        report=_report(_healthy("database")),
        integrations={},
        integrations_unavailable=True,
    )
    shopee = _item(overview, "shopee")
    assert shopee.state is HealthState.UNKNOWN
    assert shopee.reason_code == REASON_INTEGRATION_HEALTH_UNAVAILABLE


def test_unhealthy_database_wins_over_unknown_dependencies() -> None:
    error = RadarError(
        code="RAD-DB-003",
        message="unable to open database file",
        retryable=True,
        action="Verificar caminho/permissão do banco",
    )
    overview = build_home_health(
        report=_report(
            HealthCheck(
                name="database",
                state=HealthState.UNHEALTHY,
                summary="Banco indisponível",
                error=error,
            )
        ),
        integrations={},
    )
    assert overview.status is HealthState.UNHEALTHY
    database = _item(overview, "database")
    assert database.error is error
    assert overview.to_contract()["schema_version"] == "1.0"
    assert overview.to_contract()["correlation_id"] == "cid-home"
