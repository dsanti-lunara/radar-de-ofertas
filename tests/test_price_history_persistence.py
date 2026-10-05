from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from radar.application.capture_service import ManualCaptureService
from radar.domain.capture import (
    CaptureAggregate,
    CapturedOffer,
    CaptureIntake,
    CaptureSource,
    CaptureValidationError,
    Marketplace,
    MarketplacePriceHistory,
    MarketplaceProduct,
    PriceObservation,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _service(engine: Engine) -> ManualCaptureService:
    counter = itertools.count(1)
    return ManualCaptureService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        clock=lambda: FIXED_NOW,
        id_factory=lambda prefix: f"{prefix}_{next(counter):04d}",
    )


def _intake(**overrides: object) -> CaptureIntake:
    data: dict[str, object] = {
        "marketplace": Marketplace.MERCADO_LIVRE,
        "source": CaptureSource.BROWSER_EXTENSION,
        "external_id": "MLB123",
        "current_price": "79.90",
        "original_price": "109.90",
        "title": "Produto",
        "url": "https://www.mercadolivre.com.br/p/MLB123",
        "sales_count": 2300,
        "seller_name": "Loja",
        "seller_id": "SELLER-1",
    }
    data.update(overrides)
    return CaptureIntake(**data)  # type: ignore[arg-type]


def _count(engine: Engine, table: str, where: str = "") -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table} {where}").scalar()
    assert value is not None
    return int(value)


def _scalar(engine: Engine, query: str) -> Any:
    with engine.connect() as connection:
        return connection.exec_driver_sql(query).scalar()


def test_capture_appends_price_observation_with_provenance(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    result = service.capture(_intake(), correlation_id="cid-1")

    assert result.price_observation_id is not None
    history = service.get_price_history(result.marketplace_product_id)
    assert history.marketplace == "MERCADO_LIVRE"
    assert history.external_id == "MLB123"
    assert len(history.observations) == 1

    point = history.observations[0]
    assert point.price_observation_id == result.price_observation_id
    assert point.price == Decimal("79.90")
    assert point.source == "BROWSER_EXTENSION"
    assert point.observed_at == FIXED_NOW
    assert point.observed_at.tzinfo == UTC
    assert point.correlation_id == "cid-1"
    assert point.raw_capture_id == result.raw_capture_id
    assert _count(migrated_engine, "price_observation") == 1


def test_previous_observations_are_never_overwritten(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    first_at = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    second_at = first_at + timedelta(hours=6)
    first = service.capture(
        _intake(current_price="79.90", captured_at=first_at), correlation_id="cid-1"
    )
    service.capture(_intake(current_price="69.90", captured_at=second_at), correlation_id="cid-2")

    history = service.get_price_history(first.marketplace_product_id)
    assert [point.price for point in history.observations] == [
        Decimal("79.90"),
        Decimal("69.90"),
    ]
    assert [point.observed_at for point in history.observations] == [first_at, second_at]
    # The first row keeps its original price, source and observed instant.
    assert _scalar(migrated_engine, "SELECT price FROM price_observation ORDER BY observed_at") == (
        "79.90"
    )
    assert _count(migrated_engine, "price_observation") == 2


def test_repeated_capture_with_same_identity_reuses_observation(
    migrated_engine: Engine,
) -> None:
    service = _service(migrated_engine)
    first_at = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    first = service.capture(
        _intake(current_price="79.90", captured_at=first_at), correlation_id="cid-1"
    )
    repeated = service.capture(
        _intake(current_price="69.90", captured_at=first_at), correlation_id="cid-2"
    )

    # Same (marketplace_product_id, source, observed_at) identity: the
    # observation is reused and no new price is invented.
    assert repeated.price_observation_id == first.price_observation_id
    assert _count(migrated_engine, "price_observation") == 1
    history = service.get_price_history(first.marketplace_product_id)
    assert [point.price for point in history.observations] == [Decimal("79.90")]


def test_price_observation_money_is_decimal_and_timestamps_are_utc(
    migrated_engine: Engine,
) -> None:
    service = _service(migrated_engine)
    naive = datetime(2026, 10, 5, 9, 30, 0)
    result = service.capture(_intake(captured_at=naive), correlation_id="cid-utc")

    stored_price = _scalar(migrated_engine, "SELECT price FROM price_observation")
    stored_observed = _scalar(migrated_engine, "SELECT observed_at FROM price_observation")
    assert stored_price == "79.90"
    assert isinstance(stored_price, str)
    assert str(stored_observed).endswith("+00:00")

    history = service.get_price_history(result.marketplace_product_id)
    point = history.observations[0]
    assert isinstance(point.price, Decimal)
    assert point.observed_at.tzinfo == UTC


def test_price_observation_foreign_key_is_enforced(migrated_engine: Engine) -> None:
    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO price_observation "
            "(id, marketplace_product_id, price, source, observed_at, correlation_id, "
            "raw_capture_id) "
            "VALUES ('obs_fk', 'mkt_missing', '10.00', 'MANUAL_URL', "
            "'2026-10-05T12:00:00+00:00', 'cid', 'raw_missing')"
        )


class _AlwaysMissingRepository:
    """Force the identity lookup to miss so the DB constraint is exercised."""

    def __init__(self, engine: Engine) -> None:
        self._real = SqlAlchemyCaptureRepository(engine)

    def find_marketplace_product(
        self, marketplace: Marketplace, external_id: str
    ) -> MarketplaceProduct | None:
        return None

    def find_price_observation(
        self, marketplace_product_id: str, source: CaptureSource, observed_at: datetime
    ) -> PriceObservation | None:
        return self._real.find_price_observation(marketplace_product_id, source, observed_at)

    def get_price_history(self, marketplace_product_id: str) -> MarketplacePriceHistory | None:
        return self._real.get_price_history(marketplace_product_id)

    def save_capture(self, aggregate: CaptureAggregate) -> None:
        self._real.save_capture(aggregate)

    def get_captured_offer(self, candidate_id: str) -> CapturedOffer | None:
        return self._real.get_captured_offer(candidate_id)


def test_failed_capture_rolls_back_price_observation(migrated_engine: Engine) -> None:
    _service(migrated_engine).capture(_intake(), correlation_id="cid-1")

    counter = itertools.count(100)
    conflicting = ManualCaptureService(
        repository=_AlwaysMissingRepository(migrated_engine),
        clock=lambda: FIXED_NOW,
        id_factory=lambda prefix: f"{prefix}_{next(counter):04d}",
    )
    with pytest.raises(CaptureValidationError) as excinfo:
        conflicting.capture(_intake(), correlation_id="cid-2")

    assert excinfo.value.error.code == "RAD-CAP-003"
    # The failed transaction rolled back: no orphan observation or partial graph.
    assert _count(migrated_engine, "price_observation") == 1
    assert _count(migrated_engine, "offer") == 1
    assert _count(migrated_engine, "marketplace_product") == 1


def test_price_history_not_found_raises_structured_error(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    with pytest.raises(CaptureValidationError) as excinfo:
        service.get_price_history("mkt_missing")
    assert excinfo.value.error.code == "RAD-CAP-005"
