"""SQLAlchemy implementation of the Publication store (RDR-020, RDR-072).

A confirmed Publication is written together with its append-only
``PublicationEvent`` history and its ``AuditEvent`` inside **one** transaction,
so a failed write never leaves a partial record (AUT-141). The
``uq_publication_idempotency_key`` constraint makes a repeated confirmed send
idempotent at the database level (AUT-039, AUT-184); the ``publication_event``
table carries SQLite triggers (migration ``0017``) that reject UPDATE/DELETE.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.domain.audit import PUBLICATION_RECORDED, AuditEvent
from radar.domain.human_action import HumanAction
from radar.domain.knowledge import Channel
from radar.domain.publication import (
    Publication,
    PublicationEvent,
    PublicationEventType,
    PublicationStatus,
    publication_not_found_error,
)
from radar.domain.taxonomy import Brand
from radar.infrastructure.human_action_repository import human_action_to_row
from radar.infrastructure.models import AuditEventRow, PublicationEventRow, PublicationRow


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _audit_to_row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        id=event.id,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        source=event.source,
        correlation_id=event.correlation_id,
        payload=json.dumps(dict(event.payload), ensure_ascii=False, sort_keys=True),
        recorded_at=_iso(event.recorded_at),
    )


@dataclass(slots=True)
class SqlAlchemyPublicationRepository:
    """Persist and read Publications and their append-only events against SQLite."""

    engine: Engine

    def save_publication(self, publication: Publication) -> Publication:
        with Session(self.engine) as session, session.begin():
            session.add(_audit_event_to_row(publication))
            session.flush()
            session.add(_publication_to_row(publication))
            session.flush()
            session.add_all(
                _event_to_row(event, sequence=index)
                for index, event in enumerate(publication.events)
            )
        return publication

    def save_suspension(
        self,
        publication: Publication,
        human_action: HumanAction,
        audit_events: tuple[AuditEvent, ...],
    ) -> Publication:
        """Persist a suspended ``UNKNOWN`` Publication with its HumanAction.

        The publication row, its append-only events, the HumanAction and every
        audit event (``PUBLICATION_RESULT_UNKNOWN``/``HUMAN_ACTION_CREATED``) are
        written in **one transaction**, so the suspension and the intervention are
        never partially recorded (AUT-010, AUT-141). No automatic resend is ever
        performed here.
        """

        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_to_row(event))
            session.flush()
            session.add(human_action_to_row(human_action))
            session.flush()
            session.add(_publication_to_row(publication))
            session.flush()
            session.add_all(
                _event_to_row(event, sequence=index)
                for index, event in enumerate(publication.events)
            )
        return publication

    def resolve_publication(
        self,
        publication_id: str,
        *,
        status: PublicationStatus,
        external_message_id: str | None,
        published_at: datetime | None,
        event: PublicationEvent,
        audit_event: AuditEvent,
    ) -> Publication:
        """Record the auditable resolution of a suspended publication.

        The row's lifecycle status is updated (``PUBLISHED`` when the send is
        confirmed, ``FAILED`` when it is confirmed not to have happened) and the
        append-only ``RESOLVED`` event plus the resolution audit event are written
        in one transaction.
        """

        with Session(self.engine) as session, session.begin():
            row = session.get(PublicationRow, publication_id)
            if row is None:
                raise publication_not_found_error(publication_id)
            sequence = session.execute(
                select(func.count())
                .select_from(PublicationEventRow)
                .where(PublicationEventRow.publication_id == publication_id)
            ).scalar_one()
            row.status = status.value
            row.external_message_id = external_message_id
            row.published_at = None if published_at is None else _iso(published_at)
            session.add(_audit_to_row(audit_event))
            session.add(_event_to_row(event, sequence=int(sequence)))
        resolved = self.get_publication(publication_id)
        if resolved is None:  # pragma: no cover - row was just updated in this transaction
            raise publication_not_found_error(publication_id)
        return resolved

    def apply_transition(
        self,
        publication_id: str,
        *,
        status: PublicationStatus,
        event: PublicationEvent,
        audit_event: AuditEvent,
    ) -> Publication:
        """Apply an audited lifecycle transition to a Publication row.

        Used by the expire/cancel actions (TKT-27): the row's ``status`` is updated
        and the append-only event plus the action audit event are written in **one**
        transaction, so the lifecycle never advances without its history.
        """

        with Session(self.engine) as session, session.begin():
            row = session.get(PublicationRow, publication_id)
            if row is None:
                raise publication_not_found_error(publication_id)
            sequence = session.execute(
                select(func.count())
                .select_from(PublicationEventRow)
                .where(PublicationEventRow.publication_id == publication_id)
            ).scalar_one()
            row.status = status.value
            session.add(_audit_to_row(audit_event))
            session.add(_event_to_row(event, sequence=int(sequence)))
        updated = self.get_publication(publication_id)
        if updated is None:  # pragma: no cover - row was just updated in this transaction
            raise publication_not_found_error(publication_id)
        return updated

    def record_audit(self, audit_events: tuple[AuditEvent, ...]) -> None:
        """Append audit events without mutating any publication row."""

        if not audit_events:
            return
        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_to_row(event))

    def get_publication(self, publication_id: str) -> Publication | None:
        with Session(self.engine) as session:
            row = session.get(PublicationRow, publication_id)
            if row is None:
                return None
            return _publication_from_row(row, events=self._load_events(session, publication_id))

    def find_by_idempotency_key(self, idempotency_key: str) -> Publication | None:
        with Session(self.engine) as session:
            row = (
                session.execute(
                    select(PublicationRow).where(PublicationRow.idempotency_key == idempotency_key)
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return _publication_from_row(row, events=self._load_events(session, row.id))

    def list_publications_for_opportunity(self, opportunity_id: str) -> tuple[Publication, ...]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(PublicationRow)
                    .where(PublicationRow.opportunity_id == opportunity_id)
                    .order_by(PublicationRow.created_at, PublicationRow.id)
                )
                .scalars()
                .all()
            )
            return tuple(
                _publication_from_row(row, events=self._load_events(session, row.id))
                for row in rows
            )

    def find_unknown_for_opportunity(self, opportunity_id: str) -> Publication | None:
        """Return the oldest suspended (``UNKNOWN``) publication of an Opportunity.

        An open suspension blocks every new attempt for the opportunity until it is
        resolved with sufficient evidence (GRILL-002).
        """

        with Session(self.engine) as session:
            row = (
                session.execute(
                    select(PublicationRow)
                    .where(
                        PublicationRow.opportunity_id == opportunity_id,
                        PublicationRow.status == PublicationStatus.UNKNOWN.value,
                    )
                    .order_by(PublicationRow.created_at, PublicationRow.id)
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return _publication_from_row(row, events=self._load_events(session, row.id))

    def list_published_since(self, since: datetime) -> tuple[Publication, ...]:
        """Return confirmed publications with ``published_at >= since``.

        The window query feeds the deterministic cap/burst/cooldown gate, so it
        loads only the scalar fields (no event history).
        """

        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(PublicationRow)
                    .where(
                        PublicationRow.status == PublicationStatus.PUBLISHED.value,
                        PublicationRow.published_at.is_not(None),
                        PublicationRow.published_at >= _iso(since),
                    )
                    .order_by(PublicationRow.published_at, PublicationRow.id)
                )
                .scalars()
                .all()
            )
            return tuple(_publication_from_row(row, events=()) for row in rows)

    @staticmethod
    def _load_events(session: Session, publication_id: str) -> tuple[PublicationEvent, ...]:
        rows = (
            session.execute(
                select(PublicationEventRow)
                .where(PublicationEventRow.publication_id == publication_id)
                .order_by(PublicationEventRow.sequence, PublicationEventRow.id)
            )
            .scalars()
            .all()
        )
        return tuple(_event_from_row(row) for row in rows)


def _audit_event_to_row(publication: Publication) -> AuditEventRow:
    return AuditEventRow(
        id=publication.audit_event_id,
        event_type=PUBLICATION_RECORDED,
        entity_type="publication",
        entity_id=publication.publication_id,
        source="publishing",
        correlation_id=publication.correlation_id,
        payload=json.dumps(
            {
                "opportunity_id": publication.opportunity_id,
                "content_generation_id": publication.content_generation_id,
                "channel": publication.channel.value,
                "destination_id": publication.destination_id,
                "external_message_id": publication.external_message_id,
                "status": publication.status.value,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        recorded_at=_iso(publication.created_at),
    )


def _publication_to_row(publication: Publication) -> PublicationRow:
    return PublicationRow(
        id=publication.publication_id,
        opportunity_id=publication.opportunity_id,
        content_generation_id=publication.content_generation_id,
        affiliate_link_id=publication.affiliate_link_id,
        brand=publication.brand.value,
        channel=publication.channel.value,
        destination_id=publication.destination_id,
        idempotency_key=publication.idempotency_key,
        revision=publication.revision,
        status=publication.status.value,
        external_message_id=publication.external_message_id,
        published_price=publication.published_price,
        correlation_id=publication.correlation_id,
        audit_event_id=publication.audit_event_id,
        schema_version=publication.schema_version,
        created_at=_iso(publication.created_at),
        published_at=(None if publication.published_at is None else _iso(publication.published_at)),
    )


def _event_to_row(event: PublicationEvent, *, sequence: int) -> PublicationEventRow:
    return PublicationEventRow(
        id=event.event_id,
        publication_id=event.publication_id,
        sequence=sequence,
        event_type=event.event_type.value,
        correlation_id=event.correlation_id,
        payload=json.dumps(dict(event.payload), ensure_ascii=False, sort_keys=True),
        schema_version=event.schema_version,
        occurred_at=_iso(event.occurred_at),
    )


def _publication_from_row(
    row: PublicationRow, *, events: tuple[PublicationEvent, ...]
) -> Publication:
    return Publication(
        publication_id=row.id,
        opportunity_id=row.opportunity_id,
        content_generation_id=row.content_generation_id,
        affiliate_link_id=row.affiliate_link_id,
        brand=Brand(row.brand),
        channel=Channel(row.channel),
        destination_id=row.destination_id,
        idempotency_key=row.idempotency_key,
        revision=row.revision,
        status=PublicationStatus(row.status),
        external_message_id=row.external_message_id,
        published_price=row.published_price,
        correlation_id=row.correlation_id,
        audit_event_id=row.audit_event_id,
        created_at=datetime.fromisoformat(row.created_at),
        published_at=(
            None if row.published_at is None else datetime.fromisoformat(row.published_at)
        ),
        schema_version=row.schema_version,
        events=events,
    )


def _event_from_row(row: PublicationEventRow) -> PublicationEvent:
    payload: dict[str, Any] = json.loads(row.payload)
    return PublicationEvent(
        event_id=row.id,
        publication_id=row.publication_id,
        event_type=PublicationEventType(row.event_type),
        occurred_at=datetime.fromisoformat(row.occurred_at),
        correlation_id=row.correlation_id,
        payload=payload,
        schema_version=row.schema_version,
    )


__all__ = [
    "SqlAlchemyPublicationRepository",
]
