"""SQLAlchemy read model for the Publication Inbox/detail (TKT-27, RDR-061/062).

This repository composes the persisted Publication, PublicationEvent, AuditEvent,
HumanAction, Opportunity, ContentGeneration and AffiliateLink rows into the
immutable views served by :class:`~radar.application.publication_read_service.PublicationReadService`.
Nothing is recomputed or invented: the preview is the persisted ContentGeneration
and staleness is derived on read, exactly like the publication gate does.

Two entry kinds are read:

* a persisted ``Publication`` (the send side effect, including ``UNKNOWN``);
* a ``PREVIEW`` projection of an Opportunity in ``READY_TO_PUBLISH`` that still
  has validated content and an affiliate link but no open publication. The preview
  is never a persisted Publication entity (AUT-034); it only feeds the explicit
  approval screen, and the approval itself goes through the audited publish
  contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.application.content_service import ContentGenerationService
from radar.application.publication_read_service import (
    KIND_PREVIEW,
    KIND_PUBLICATION,
    VALIDATION_SOURCE_CREATION,
    VALIDATION_SOURCE_REVALIDATION,
    ContentPreviewView,
    PublicationDetail,
    PublicationInboxItem,
    PublicationLinkView,
    PublicationProductView,
    PublicationTimelineEntry,
    PublicationValidationView,
)
from radar.domain.audit import PUBLICATION_REVALIDATED
from radar.domain.content import ContentGeneration, ContentGenerationStatus
from radar.domain.opportunity import OpportunityState
from radar.domain.publication import (
    OPEN_PUBLICATION_STATUSES,
    Publication,
)
from radar.infrastructure.human_action_repository import human_action_from_row
from radar.infrastructure.models import (
    AffiliateLinkRow,
    AuditEventRow,
    CandidateRow,
    HumanActionRow,
    MarketplaceProductRow,
    OfferRow,
    OpportunityRow,
    ProductRow,
    PublicationEventRow,
    PublicationRow,
)
from radar.infrastructure.publication_repository import SqlAlchemyPublicationRepository

_ENTITY_PUBLICATION = "publication"
_SOURCE_PUBLICATION_EVENT = "publication_event"

_OPEN_STATUS_VALUES = tuple(sorted(status.value for status in OPEN_PUBLICATION_STATUSES))


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


@dataclass(slots=True)
class SqlAlchemyPublicationReadRepository:
    """Serve the Publication Inbox/detail read models on SQLite."""

    engine: Engine
    content: ContentGenerationService

    # -- Inbox --------------------------------------------------------------

    def list_publications(self) -> tuple[PublicationInboxItem, ...]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(PublicationRow).order_by(
                        PublicationRow.created_at.desc(), PublicationRow.id.desc()
                    )
                )
                .scalars()
                .all()
            )
            return tuple(self._inbox_item(session, row) for row in rows)

    def list_pending_previews(self) -> tuple[PublicationInboxItem, ...]:
        with Session(self.engine) as session:
            opportunities = (
                session.execute(
                    select(OpportunityRow)
                    .where(OpportunityRow.state == OpportunityState.READY_TO_PUBLISH.value)
                    .order_by(OpportunityRow.updated_at.desc(), OpportunityRow.id.desc())
                )
                .scalars()
                .all()
            )
            items: list[PublicationInboxItem] = []
            for opportunity in opportunities:
                item = self._preview_item(session, opportunity)
                if item is not None:
                    items.append(item)
            return tuple(items)

    def _inbox_item(self, session: Session, row: PublicationRow) -> PublicationInboxItem:
        events = self._event_rows(session, row.id)
        updated_at = events[-1].occurred_at if events else (row.published_at or row.created_at)
        return PublicationInboxItem(
            entry_id=row.id,
            kind=KIND_PUBLICATION,
            publication_id=row.id,
            opportunity_id=row.opportunity_id,
            content_generation_id=row.content_generation_id,
            brand=row.brand,
            channel=row.channel,
            destination_id=row.destination_id,
            status=row.status,
            revision=row.revision,
            external_message_id=row.external_message_id,
            published_price=row.published_price,
            product=self._product_view(session, row.opportunity_id),
            last_validation=self._last_validation(
                session, publication_id=row.id, fallback_at=row.created_at
            ),
            updated_at=updated_at,
        )

    def _preview_item(
        self, session: Session, opportunity: OpportunityRow
    ) -> PublicationInboxItem | None:
        if self._has_open_publication(session, opportunity.id):
            return None
        content = self._latest_content(opportunity.id)
        if content is None or content.status is not ContentGenerationStatus.VALIDATED:
            return None
        if self._link_row(session, opportunity.id) is None:
            return None
        stale = self.content.is_stale(content)
        return PublicationInboxItem(
            entry_id=f"preview:{opportunity.id}",
            kind=KIND_PREVIEW,
            publication_id=None,
            opportunity_id=opportunity.id,
            content_generation_id=content.content_generation_id,
            brand=opportunity.brand,
            channel=content.channel.value,
            destination_id=None,
            status="STALE" if stale else "READY",
            revision=None,
            external_message_id=None,
            published_price=None,
            product=self._product_view(session, opportunity.id),
            last_validation=PublicationValidationView(
                validated_at=_iso(content.created_at),
                allowed=True,
                reason_code=None,
                source=VALIDATION_SOURCE_CREATION,
            ),
            updated_at=_iso(content.created_at),
        )

    # -- Detail -------------------------------------------------------------

    def get_publication_detail(self, publication_id: str) -> PublicationDetail | None:
        with Session(self.engine) as session:
            row = session.get(PublicationRow, publication_id)
            if row is None:
                return None
            publication = SqlAlchemyPublicationRepository(self.engine).get_publication(
                publication_id
            )
            return PublicationDetail(
                kind=KIND_PUBLICATION,
                opportunity_id=row.opportunity_id,
                publication=publication,
                product=self._product_view(session, row.opportunity_id),
                preview=self._preview(row.content_generation_id),
                link=self._link_view(session, row.affiliate_link_id),
                revision=row.revision,
                external_message_id=row.external_message_id,
                last_validation=self._last_validation(
                    session, publication_id=row.id, fallback_at=row.created_at
                ),
                timeline=() if publication is None else self._timeline(session, publication),
                human_actions=self._human_actions(session, row.id),
            )

    def get_preview_detail(self, opportunity_id: str) -> PublicationDetail | None:
        with Session(self.engine) as session:
            opportunity = session.get(OpportunityRow, opportunity_id)
            if opportunity is None or opportunity.state != OpportunityState.READY_TO_PUBLISH.value:
                return None
            if self._has_open_publication(session, opportunity_id):
                return None
            content = self._latest_content(opportunity_id)
            if content is None or content.status is not ContentGenerationStatus.VALIDATED:
                return None
            link = self._link_row(session, opportunity_id)
            if link is None:
                return None
            return PublicationDetail(
                kind=KIND_PREVIEW,
                opportunity_id=opportunity_id,
                publication=None,
                product=self._product_view(session, opportunity_id),
                preview=self._preview_from_content(content),
                link=self._link_view(session, link.id),
                revision=None,
                external_message_id=None,
                last_validation=PublicationValidationView(
                    validated_at=_iso(content.created_at),
                    allowed=True,
                    reason_code=None,
                    source=VALIDATION_SOURCE_CREATION,
                ),
                timeline=self._preview_timeline(session, opportunity_id, content),
                human_actions=(),
            )

    # -- Views --------------------------------------------------------------

    def _product_view(self, session: Session, opportunity_id: str) -> PublicationProductView:
        row = session.execute(
            select(OpportunityRow, CandidateRow, OfferRow, MarketplaceProductRow, ProductRow)
            .join(CandidateRow, OpportunityRow.candidate_id == CandidateRow.id)
            .join(OfferRow, CandidateRow.offer_id == OfferRow.id)
            .join(
                MarketplaceProductRow, OfferRow.marketplace_product_id == MarketplaceProductRow.id
            )
            .outerjoin(ProductRow, MarketplaceProductRow.product_id == ProductRow.id)
            .where(OpportunityRow.id == opportunity_id)
        ).first()
        if row is None:
            return PublicationProductView(
                marketplace=None,
                external_id=None,
                title=None,
                url=None,
                brand=None,
                current_price=None,
            )
        opportunity, _candidate, offer, marketplace, product = row
        return PublicationProductView(
            marketplace=marketplace.marketplace,
            external_id=marketplace.external_id,
            title=marketplace.title,
            url=marketplace.url,
            brand=(product.brand if product is not None else None) or opportunity.brand,
            current_price=offer.current_price,
        )

    def _latest_content(self, opportunity_id: str) -> ContentGeneration | None:
        records = self.content.repository.list_content_generations(opportunity_id)
        return records[-1] if records else None

    def _preview(self, content_generation_id: str) -> ContentPreviewView | None:
        record = self.content.repository.get_content_generation(content_generation_id)
        if record is None:
            return None
        return self._preview_from_content(record)

    def _preview_from_content(self, record: ContentGeneration) -> ContentPreviewView:
        stale = self.content.is_stale(record)
        return ContentPreviewView(
            content_generation_id=record.content_generation_id,
            channel=record.channel.value,
            status=(ContentGenerationStatus.STALE if stale else record.status).value,
            stale=stale,
            renderer_version=record.renderer_version,
            headline=record.rendered.headline,
            body=record.rendered.body,
            cta=record.rendered.cta,
            text=record.rendered.text,
            price=record.rendered.price,
            affiliate_url=record.rendered.affiliate_url,
            disclosure=record.rendered.disclosure,
            tracking=dict(record.rendered.tracking),
        )

    def _link_row(self, session: Session, opportunity_id: str) -> AffiliateLinkRow | None:
        return (
            session.execute(
                select(AffiliateLinkRow)
                .where(AffiliateLinkRow.opportunity_id == opportunity_id)
                .order_by(AffiliateLinkRow.created_at, AffiliateLinkRow.id)
            )
            .scalars()
            .first()
        )

    def _link_view(self, session: Session, affiliate_link_id: str) -> PublicationLinkView | None:
        row = session.get(AffiliateLinkRow, affiliate_link_id)
        if row is None:
            return None
        return PublicationLinkView(
            affiliate_link_id=row.id,
            affiliate_url=row.affiliate_url,
            productive=bool(row.productive),
            generation_method=row.generation_method,
            status=row.status,
            tracking_context_id=row.tracking_context_id,
            tracking_internal_reference=row.tracking_internal_reference,
            tracking_label=row.tracking_label,
            tracking_mapping_version=row.tracking_mapping_version,
        )

    def _has_open_publication(self, session: Session, opportunity_id: str) -> bool:
        return (
            session.execute(
                select(PublicationRow.id)
                .where(
                    PublicationRow.opportunity_id == opportunity_id,
                    PublicationRow.status.in_(_OPEN_STATUS_VALUES),
                )
                .limit(1)
            ).first()
            is not None
        )

    def _last_validation(
        self, session: Session, *, publication_id: str, fallback_at: str
    ) -> PublicationValidationView:
        row = session.execute(
            select(AuditEventRow)
            .where(
                AuditEventRow.event_type == PUBLICATION_REVALIDATED,
                AuditEventRow.entity_type == _ENTITY_PUBLICATION,
                AuditEventRow.entity_id == publication_id,
            )
            .order_by(AuditEventRow.recorded_at.desc(), AuditEventRow.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return PublicationValidationView(
                validated_at=fallback_at,
                allowed=True,
                reason_code=None,
                source=VALIDATION_SOURCE_CREATION,
            )
        payload = {} if row.payload is None else json.loads(row.payload)
        return PublicationValidationView(
            validated_at=row.recorded_at,
            allowed=payload.get("allowed") is True,
            reason_code=payload.get("reason_code"),
            source=VALIDATION_SOURCE_REVALIDATION,
        )

    def _event_rows(self, session: Session, publication_id: str) -> list[PublicationEventRow]:
        return list(
            session.execute(
                select(PublicationEventRow)
                .where(PublicationEventRow.publication_id == publication_id)
                .order_by(PublicationEventRow.sequence, PublicationEventRow.id)
            )
            .scalars()
            .all()
        )

    def _timeline(
        self, session: Session, publication: Publication
    ) -> tuple[PublicationTimelineEntry, ...]:
        entries: list[PublicationTimelineEntry] = [
            PublicationTimelineEntry(
                event_type=event.event_type.value,
                source=_SOURCE_PUBLICATION_EVENT,
                occurred_at=_iso(event.occurred_at),
                correlation_id=event.correlation_id,
                payload=dict(event.payload),
            )
            for event in publication.events
        ]
        audit_rows = (
            session.execute(
                select(AuditEventRow)
                .where(
                    AuditEventRow.entity_type == _ENTITY_PUBLICATION,
                    AuditEventRow.entity_id == publication.publication_id,
                )
                .order_by(AuditEventRow.recorded_at, AuditEventRow.id)
            )
            .scalars()
            .all()
        )
        entries.extend(
            PublicationTimelineEntry(
                event_type=row.event_type,
                source=row.source,
                occurred_at=row.recorded_at,
                correlation_id=row.correlation_id,
                payload={} if row.payload is None else json.loads(row.payload),
            )
            for row in audit_rows
        )
        return tuple(sorted(entries, key=lambda entry: (entry.occurred_at, entry.event_type)))

    def _preview_timeline(
        self, session: Session, opportunity_id: str, content: ContentGeneration
    ) -> tuple[PublicationTimelineEntry, ...]:
        rows = (
            session.execute(
                select(AuditEventRow)
                .where(
                    or_(
                        AuditEventRow.entity_id == opportunity_id,
                        AuditEventRow.entity_id == content.content_generation_id,
                    )
                )
                .order_by(AuditEventRow.recorded_at, AuditEventRow.id)
            )
            .scalars()
            .all()
        )
        return tuple(
            PublicationTimelineEntry(
                event_type=row.event_type,
                source=row.source,
                occurred_at=row.recorded_at,
                correlation_id=row.correlation_id,
                payload={} if row.payload is None else json.loads(row.payload),
            )
            for row in rows
        )

    def _human_actions(self, session: Session, publication_id: str) -> tuple[dict[str, Any], ...]:
        rows = (
            session.execute(
                select(HumanActionRow)
                .where(
                    HumanActionRow.entity_type == _ENTITY_PUBLICATION,
                    HumanActionRow.entity_id == publication_id,
                )
                .order_by(HumanActionRow.created_at, HumanActionRow.id)
            )
            .scalars()
            .all()
        )
        return tuple(human_action_from_row(row).to_contract() for row in rows)


__all__ = [
    "SqlAlchemyPublicationReadRepository",
]
