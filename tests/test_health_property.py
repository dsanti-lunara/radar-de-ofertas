from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from radar.domain.health import HealthCheck, HealthState, aggregate_health

pytestmark = pytest.mark.unit

_STATES = st.sampled_from(list(HealthState))


@given(st.lists(_STATES, min_size=1))
def test_aggregate_precedence(states: list[HealthState]) -> None:
    checks = [
        HealthCheck(name=f"check-{index}", state=state, summary="s")
        for index, state in enumerate(states)
    ]
    result = aggregate_health(checks)
    if HealthState.UNHEALTHY in states:
        assert result is HealthState.UNHEALTHY
    elif HealthState.UNKNOWN in states or HealthState.DEGRADED in states:
        assert result is HealthState.DEGRADED
    else:
        assert result is HealthState.HEALTHY


def test_empty_aggregate_is_unknown() -> None:
    assert aggregate_health([]) is HealthState.UNKNOWN
