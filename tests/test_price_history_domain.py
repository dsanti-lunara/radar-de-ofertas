from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from radar.domain.capture import (
    CaptureSource,
    MarketplacePriceHistory,
    PriceHistoryPoint,
    price_observation_identity,
)

pytestmark = pytest.mark.unit

_OBSERVED_AT = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def test_price_observation_identity_is_stable_across_timezones() -> None:
    shifted = _OBSERVED_AT.astimezone(timezone(timedelta(hours=-3)))
    assert price_observation_identity(
        "mkt_1", CaptureSource.MANUAL_URL, _OBSERVED_AT
    ) == price_observation_identity("mkt_1", CaptureSource.MANUAL_URL, shifted)


def test_price_observation_identity_distinguishes_source_and_instant() -> None:
    base = price_observation_identity("mkt_1", CaptureSource.MANUAL_URL, _OBSERVED_AT)
    assert base != price_observation_identity(
        "mkt_1", CaptureSource.BROWSER_EXTENSION, _OBSERVED_AT
    )
    assert base != price_observation_identity(
        "mkt_1", CaptureSource.MANUAL_URL, _OBSERVED_AT + timedelta(seconds=1)
    )
    assert base != price_observation_identity("mkt_2", CaptureSource.MANUAL_URL, _OBSERVED_AT)


def test_price_history_contract_serializes_decimal_and_utc() -> None:
    history = MarketplacePriceHistory(
        marketplace_product_id="mkt_1",
        marketplace="MERCADO_LIVRE",
        external_id="MLB123",
        observations=(
            PriceHistoryPoint(
                price_observation_id="obs_1",
                price=Decimal("79.90"),
                observed_at=_OBSERVED_AT,
                source="MANUAL_URL",
                correlation_id="cid-1",
                raw_capture_id="raw_1",
                original_price=Decimal("109.90"),
                shipping_cost=Decimal("0.00"),
            ),
        ),
    )

    contract = history.to_contract(correlation_id="cid-query")
    assert contract["schema_version"] == "1.0"
    assert contract["status"] == "OK"
    assert contract["correlation_id"] == "cid-query"
    assert contract["observation_count"] == 1
    point = contract["observations"][0]
    assert point["price"] == "79.90"
    assert point["original_price"] == "109.90"
    assert point["shipping_cost"] == "0.00"
    assert point["observed_at"] == "2026-10-05T12:00:00+00:00"
    assert point["raw_capture_id"] == "raw_1"
    assert point["correlation_id"] == "cid-1"
