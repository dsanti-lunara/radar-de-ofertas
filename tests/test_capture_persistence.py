from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import inspect
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
    MarketplaceProduct,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

_TABLES = (
    "product",
    "marketplace_product",
    "offer",
    "raw_capture",
    "evidence",
    "discovery_event",
    "candidate",
    "audit_event",
)


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


def test_capture_materializes_distinct_entities(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    result = service.capture(_intake(), correlation_id="cid-1")

    assert (
        len(
            {result.product_id, result.marketplace_product_id, result.offer_id, result.candidate_id}
        )
        == 4
    )
    assert result.candidate_state == "NEW"
    assert result.duplicate_identity is False
    assert result.correlation_id == "cid-1"

    stored = service.get_candidate(result.candidate_id)
    assert stored.candidate_id == result.candidate_id
    assert stored.product_id == result.product_id
    assert stored.marketplace_product_id == result.marketplace_product_id
    assert stored.offer_id == result.offer_id
    assert stored.external_id == "MLB123"
    assert stored.marketplace == "MERCADO_LIVRE"

    assert _count(migrated_engine, "product") == 1
    assert _count(migrated_engine, "marketplace_product") == 1
    assert _count(migrated_engine, "offer") == 1
    assert _count(migrated_engine, "candidate") == 1


def test_repeated_capture_does_not_duplicate_identity(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    first = service.capture(_intake(), correlation_id="cid-1")
    second = service.capture(_intake(current_price="69.90"), correlation_id="cid-2")

    assert second.marketplace_product_id == first.marketplace_product_id
    assert second.product_id == first.product_id
    assert second.offer_id != first.offer_id
    assert second.candidate_id != first.candidate_id
    assert second.duplicate_identity is True

    assert _count(migrated_engine, "product") == 1
    assert _count(migrated_engine, "marketplace_product") == 1
    assert _count(migrated_engine, "offer") == 2
    assert _count(migrated_engine, "candidate") == 2
    # Raw captures and provenance are appended for every capture.
    assert _count(migrated_engine, "raw_capture") == 2
    assert _count(migrated_engine, "discovery_event") == 2


def test_unique_constraint_blocks_duplicate_identity(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    service.capture(_intake(), correlation_id="cid-1")
    product_id = _scalar(migrated_engine, "SELECT id FROM product")
    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO marketplace_product "
            "(id, product_id, marketplace, external_id, first_seen_at, last_seen_at) "
            "VALUES ('mkt_dup', ?, 'MERCADO_LIVRE', 'MLB123', '2026-10-05T00:00:00+00:00', "
            "'2026-10-05T00:00:00+00:00')",
            (product_id,),
        )


def test_invalid_capture_stops_before_persisting(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    with pytest.raises(CaptureValidationError):
        service.capture(_intake(url="javascript:alert(1)"), correlation_id="cid-x")
    with pytest.raises(CaptureValidationError):
        service.capture(_intake(current_price=79.9), correlation_id="cid-x")

    for table in _TABLES:
        assert _count(migrated_engine, table) == 0, table


def test_raw_capture_is_sanitized_and_evidence_is_persisted(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    service.capture(
        _intake(title="Cafeteira\n\n  12L \x00 ", external_id="MLB999"),
        correlation_id="cid-1",
    )
    payload = json.loads(_scalar(migrated_engine, "SELECT payload FROM raw_capture"))
    assert payload["product"]["title"] == "Cafeteira 12L"
    assert payload["product"]["external_id"] == "MLB999"
    # Full HTML is never stored, only the structured payload.
    assert "<html" not in json.dumps(payload).lower()

    assert _count(migrated_engine, "evidence", "WHERE entity_type = 'offer'") >= 1
    assert (
        _scalar(
            migrated_engine,
            "SELECT value FROM evidence WHERE field_name = 'current_price'",
        )
        == "79.90"
    )
    assert (
        _scalar(
            migrated_engine,
            "SELECT confidence FROM evidence WHERE field_name = 'current_price'",
        )
        is None
    )


def test_discovery_event_and_audit_preserve_source_and_correlation(
    migrated_engine: Engine,
) -> None:
    service = _service(migrated_engine)
    result = service.capture(_intake(source=CaptureSource.MANUAL_URL), correlation_id="cid-42")

    assert _scalar(migrated_engine, "SELECT source FROM discovery_event") == "MANUAL_URL"
    assert _scalar(migrated_engine, "SELECT correlation_id FROM discovery_event") == "cid-42"
    assert _scalar(migrated_engine, "SELECT correlation_id FROM audit_event") == "cid-42"
    assert _scalar(migrated_engine, "SELECT source FROM audit_event") == "MANUAL_URL"
    assert _scalar(migrated_engine, "SELECT event_type FROM audit_event") == "CAPTURE_RECEIVED"
    assert _scalar(migrated_engine, "SELECT entity_id FROM audit_event") == result.candidate_id
    assert _scalar(migrated_engine, "SELECT correlation_id FROM candidate") == "cid-42"


def test_migration_creates_expected_tables(migrated_engine: Engine) -> None:
    tables = set(inspect(migrated_engine).get_table_names())
    assert set(_TABLES).issubset(tables)


class _AlwaysMissingRepository:
    """Force the identity lookup to miss so the DB constraint is exercised."""

    def __init__(self, engine: Engine) -> None:
        self._real = SqlAlchemyCaptureRepository(engine)

    def find_marketplace_product(
        self, marketplace: Marketplace, external_id: str
    ) -> MarketplaceProduct | None:
        return None

    def save_capture(self, aggregate: CaptureAggregate) -> None:
        self._real.save_capture(aggregate)

    def get_captured_offer(self, candidate_id: str) -> CapturedOffer | None:
        return self._real.get_captured_offer(candidate_id)


def test_identity_race_fails_closed_without_partial_write(migrated_engine: Engine) -> None:
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
    assert excinfo.value.error.retryable is True
    # The failed transaction rolled back: no partial graph from the second capture.
    assert _count(migrated_engine, "product") == 1
    assert _count(migrated_engine, "marketplace_product") == 1
    assert _count(migrated_engine, "offer") == 1
    assert _count(migrated_engine, "raw_capture") == 1
    assert _count(migrated_engine, "evidence") == 7
    assert _count(migrated_engine, "candidate") == 1
    assert _count(migrated_engine, "audit_event") == 1
