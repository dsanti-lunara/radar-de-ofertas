from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from radar.api.app import create_app
from radar.application.operations_service import OperationsService
from radar.application.publication_service import PublicationService
from radar.domain.knowledge import Channel
from radar.domain.operations import (
    AutomationPolicy,
    ChannelCompliancePolicy,
    build_automation_policy,
    build_compliance_policy,
)
from radar.domain.publication import (
    PUBLICATION_BLOCKED,
    REASON_QUIET_HOURS,
    PublicationError,
    PublicationStatus,
    build_publication,
    build_publication_policy,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.domain.tracking import build_tracking_label_mapping
from radar.infrastructure.affiliate_link_repository import SqlAlchemyAffiliateLinkRepository
from radar.infrastructure.content_repository import SqlAlchemyContentGenerationRepository
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.operations_repository import SqlAlchemyOperationsRepository
from radar.infrastructure.opportunity_repository import SqlAlchemyWorkflowRepository
from radar.infrastructure.publication_publisher import FakePublisher
from radar.infrastructure.publication_repository import SqlAlchemyPublicationRepository
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.integration

ASSISTED_POLICY: AutomationPolicy = build_automation_policy(
    {"schema_version": "1.0", "policy_version": "assisted", "default_mode": "ASSISTED"}
)
ACTIVE_COMPLIANCE: ChannelCompliancePolicy = build_compliance_policy(
    {"schema_version": "1.0", "policy_version": "active", "status": "ACTIVE"}
)
FROZEN_NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class _NeverStale:
    def is_stale(self, record: Any) -> bool:
        return False


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def _mapping() -> Any:
    return build_tracking_label_mapping(
        {
            "schema_version": "1.0",
            "mapping_version": "tracking-labels-test",
            "entries": [
                {
                    "internal_reference": "RADAR_BEAUTY:MERCADO_LIVRE",
                    "marketplace": "MERCADO_LIVRE",
                    "label": "rbtgoffer",
                }
            ],
        }
    )


def _client(database_url: str) -> TestClient:
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=Settings(database_url=database_url),
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            tracking_labels=_mapping(),
            automation_policy=ASSISTED_POLICY,
            compliance_policy=ACTIVE_COMPLIANCE,
        )
    )


def _ready_content(client: TestClient) -> tuple[str, str]:
    capture = client.post(
        "/captures/manual",
        json={
            "schema_version": "1.0",
            "marketplace": "MERCADO_LIVRE",
            "source": "BROWSER_EXTENSION",
            "product": {
                "external_id": "MLB-PERSIST",
                "title": "Perfume",
                "url": "https://www.mercadolivre.com.br/p/MLB-PERSIST",
                "category": "Perfumes",
            },
            "offer": {"current_price": "80.00", "sales_count": 2300, "seller": {"name": "Loja"}},
            "captured_at": "2026-10-06T12:00:00+00:00",
        },
    )
    assert capture.status_code == 201, capture.text
    candidate_id = capture.json()["candidate_id"]
    evaluation = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json={
            "schema_version": "1.0",
            "brand": "RADAR_BEAUTY",
            "deal": {"price_opportunity": 100, "seller_quality": 100, "demand": 100},
            "confidence": {
                "source_reliability": 100,
                "freshness": 100,
                "completeness": 100,
                "price_history_depth": 100,
                "cross_validation": 100,
            },
        },
    )
    assert evaluation.status_code == 201, evaluation.text
    advanced = client.post(
        f"/candidates/{candidate_id}/opportunities",
        json={"schema_version": "1.0"},
    )
    assert advanced.status_code == 201, advanced.text
    opportunity_id = advanced.json()["opportunity"]["opportunity_id"]
    link = client.post(f"/candidates/{candidate_id}/affiliate-link", json={"schema_version": "1.0"})
    assert link.status_code == 201, link.text
    generated = client.post(
        f"/opportunities/{opportunity_id}/content-generations",
        json={"schema_version": "1.0", "channel": "TELEGRAM"},
    )
    assert generated.status_code == 201, generated.text
    for target in ("LINK_READY", "CONTENT_PENDING", "READY_TO_PUBLISH"):
        transition = client.post(
            f"/opportunities/{opportunity_id}/transitions",
            json={"schema_version": "1.0", "target_state": target},
        )
        assert transition.status_code == 200, transition.text
    return opportunity_id, generated.json()["content_generation_id"]


def _publish(client: TestClient, opportunity_id: str, content_generation_id: str) -> dict[str, Any]:
    response = client.post(
        f"/opportunities/{opportunity_id}/publications",
        json={
            "schema_version": "1.0",
            "content_generation_id": content_generation_id,
            "destination_id": "dest-tg-sandbox",
            "idempotency_key": "publish:persist:1",
            "publication_approved": True,
        },
        headers={"X-Correlation-ID": "cid-persist"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_publication_is_persisted_with_events_and_queryable(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    opportunity_id, content_generation_id = _ready_content(client)
    body = _publish(client, opportunity_id, content_generation_id)

    engine = create_database_engine(migrated_database_url)
    try:
        repository = SqlAlchemyPublicationRepository(engine=engine)
        stored = repository.get_publication(body["publication_id"])
        assert stored is not None
        assert stored.status is PublicationStatus.PUBLISHED
        assert stored.channel is Channel.TELEGRAM
        assert stored.external_message_id == body["external_message_id"]
        assert [event.event_type.value for event in stored.events] == ["CREATED", "PUBLISHED"]

        by_key = repository.find_by_idempotency_key("publish:persist:1")
        assert by_key is not None
        assert by_key.publication_id == body["publication_id"]

        assert len(repository.list_publications_for_opportunity(opportunity_id)) == 1
        recent = repository.list_published_since(datetime.now(UTC) - timedelta(days=1))
        assert any(item.publication_id == body["publication_id"] for item in recent)

        assert _count(engine, "publication") == 1
        assert _count(engine, "publication_event") == 2
    finally:
        engine.dispose()


def test_duplicate_idempotency_key_rolls_back_without_partial_records(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    opportunity_id, content_generation_id = _ready_content(client)
    body = _publish(client, opportunity_id, content_generation_id)

    engine = create_database_engine(migrated_database_url)
    try:
        repository = SqlAlchemyPublicationRepository(engine=engine)
        existing = repository.get_publication(body["publication_id"])
        assert existing is not None
        audit_before = _count(engine, "audit_event")
        events_before = _count(engine, "publication_event")

        duplicate = dataclasses.replace(
            existing,
            publication_id="pub-duplicate",
            audit_event_id="aud-duplicate",
        )
        with pytest.raises(IntegrityError):
            repository.save_publication(duplicate)

        assert _count(engine, "publication") == 1
        assert _count(engine, "publication_event") == events_before
        assert _count(engine, "audit_event") == audit_before
    finally:
        engine.dispose()


def test_publication_event_is_append_only(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    opportunity_id, content_generation_id = _ready_content(client)
    _publish(client, opportunity_id, content_generation_id)

    engine = create_database_engine(migrated_database_url)
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE publication_event SET event_type = 'ERROR'"))
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("DELETE FROM publication_event"))
        assert _count(engine, "publication_event") == 2
    finally:
        engine.dispose()


def test_publication_requires_existing_entities(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    opportunity_id, content_generation_id = _ready_content(client)
    _publish(client, opportunity_id, content_generation_id)

    engine = create_database_engine(migrated_database_url)
    try:
        repository = SqlAlchemyPublicationRepository(engine=engine)
        stored = repository.find_by_idempotency_key("publish:persist:1")
        assert stored is not None
        orphan = build_publication(
            opportunity_id="opp_missing",
            content_generation_id=content_generation_id,
            affiliate_link_id=stored.affiliate_link_id,
            brand=stored.brand,
            channel=stored.channel,
            destination_id="dest",
            idempotency_key="publish:orphan",
            published_price="80.00",
            external_message_id="fake",
            correlation_id="cid",
            audit_event_id="aud-orphan",
            created_at=FROZEN_NOW,
            published_at=FROZEN_NOW,
            publication_id="pub-orphan",
        )
        with pytest.raises(IntegrityError):
            repository.save_publication(orphan)
    finally:
        engine.dispose()


def test_quiet_hours_block_with_controlled_clock(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    opportunity_id, content_generation_id = _ready_content(client)

    engine = create_database_engine(migrated_database_url)
    try:
        service = PublicationService(
            repository=SqlAlchemyPublicationRepository(engine=engine),
            opportunities=SqlAlchemyWorkflowRepository(engine=engine),
            content=SqlAlchemyContentGenerationRepository(engine=engine),
            revalidation=_NeverStale(),
            links=SqlAlchemyAffiliateLinkRepository(engine=engine),
            authorizer=OperationsService(
                store=SqlAlchemyOperationsRepository(engine=engine),
                automation_policy=ASSISTED_POLICY,
                compliance_policy=ACTIVE_COMPLIANCE,
            ),
            policy=build_publication_policy(
                {
                    "policy_version": "quiet-1",
                    "timezone": "America/Maceio",
                    "quiet_windows": [{"start": "22:00", "end": "07:00"}],
                }
            ),
            publisher=FakePublisher(),
            # 02:00 UTC == 23:00 America/Maceio, inside the quiet window.
            clock=_Clock(datetime(2026, 10, 6, 2, 0, tzinfo=UTC)),
        )

        with pytest.raises(PublicationError) as excinfo:
            service.publish(
                opportunity_id,
                content_generation_id=content_generation_id,
                destination_id="dest-tg-sandbox",
                idempotency_key="publish:quiet",
                publication_approved=True,
                correlation_id="cid-quiet",
            )

        assert excinfo.value.error.code == PUBLICATION_BLOCKED
        assert excinfo.value.error.context["reason_code"] == REASON_QUIET_HOURS
        assert _count(engine, "publication") == 0
    finally:
        engine.dispose()
