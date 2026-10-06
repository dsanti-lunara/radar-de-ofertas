"""SQLAlchemy persistence for AffiliateLinks (RDR-018, RDR-070).

The AffiliateLink and its ``AuditEvent`` are written in **one** transaction, so a
failed write never leaves a partial record (AUT-141). The
``uq_affiliate_link_opportunity_tracking`` unique constraint makes generation
idempotent: a repeated or concurrent request for the same Opportunity + label can
never create a second link (AUT-039, AUT-132). The literal ``affiliate_url`` is
stored unchanged and the internal tracking context is kept separate from the
external label.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.application.affiliate_link_service import CandidateLinkContext
from radar.domain.affiliate_link import (
    AffiliateLink,
    AffiliateLinkStatus,
    LinkGenerationMethod,
)
from radar.domain.audit import AFFILIATE_LINK_GENERATED
from radar.domain.capture import Marketplace
from radar.domain.taxonomy import Brand
from radar.domain.tracking import TrackingContext
from radar.infrastructure.models import (
    AffiliateLinkRow,
    AuditEventRow,
    CandidateRow,
    MarketplaceProductRow,
    OfferRow,
    OpportunityRow,
)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


@dataclass(slots=True)
class SqlAlchemyAffiliateLinkRepository:
    """Persist and read AffiliateLinks against SQLite."""

    engine: Engine

    def get_candidate_link_context(self, candidate_id: str) -> CandidateLinkContext | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(
                    CandidateRow.id,
                    MarketplaceProductRow.marketplace,
                    MarketplaceProductRow.external_id,
                    MarketplaceProductRow.url,
                    CandidateRow.correlation_id,
                )
                .join(OfferRow, CandidateRow.offer_id == OfferRow.id)
                .join(
                    MarketplaceProductRow,
                    OfferRow.marketplace_product_id == MarketplaceProductRow.id,
                )
                .where(CandidateRow.id == candidate_id)
            ).one_or_none()
        if row is None:
            return None
        return CandidateLinkContext(
            candidate_id=row[0],
            marketplace=Marketplace(row[1]),
            external_id=row[2],
            original_url=row[3],
            correlation_id=row[4],
        )

    def find_link(self, opportunity_id: str, tracking_label: str) -> AffiliateLink | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(AffiliateLinkRow).where(
                    AffiliateLinkRow.opportunity_id == opportunity_id,
                    AffiliateLinkRow.tracking_label == tracking_label,
                )
            ).scalar_one_or_none()
            return None if row is None else _link_from_row(row)

    def save_link(self, link: AffiliateLink) -> AffiliateLink:
        """Persist the link and its audit event atomically (idempotent)."""

        try:
            with Session(self.engine) as session, session.begin():
                session.add(_audit_event_to_row(link))
                session.flush()
                session.add(_link_to_row(link))
        except IntegrityError:
            existing = self.find_link(link.opportunity_id, link.tracking.external_label or "")
            if existing is not None:
                return existing
            raise
        return link

    def find_link_for_opportunity(self, opportunity_id: str) -> AffiliateLink | None:
        """Return the most recent validated link of one Opportunity, if any."""

        with Session(self.engine) as session:
            row = session.execute(
                select(AffiliateLinkRow)
                .where(AffiliateLinkRow.opportunity_id == opportunity_id)
                .order_by(AffiliateLinkRow.created_at.desc(), AffiliateLinkRow.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            return None if row is None else _link_from_row(row)

    def list_links(self, candidate_id: str) -> tuple[AffiliateLink, ...]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(AffiliateLinkRow)
                    .join(OpportunityRow, AffiliateLinkRow.opportunity_id == OpportunityRow.id)
                    .where(OpportunityRow.candidate_id == candidate_id)
                    .order_by(AffiliateLinkRow.created_at.asc(), AffiliateLinkRow.id.asc())
                )
                .scalars()
                .all()
            )
        return tuple(_link_from_row(row) for row in rows)

    def get_link(self, affiliate_link_id: str) -> AffiliateLink | None:
        with Session(self.engine) as session:
            row = session.get(AffiliateLinkRow, affiliate_link_id)
            return None if row is None else _link_from_row(row)


def _audit_event_to_row(link: AffiliateLink) -> AuditEventRow:
    return AuditEventRow(
        id=link.audit_event_id,
        event_type=AFFILIATE_LINK_GENERATED,
        entity_type="affiliate_link",
        entity_id=link.affiliate_link_id,
        source="link",
        correlation_id=link.correlation_id,
        payload=json.dumps(
            {
                "opportunity_id": link.opportunity_id,
                "marketplace": link.marketplace.value,
                "generation_method": link.generation_method.value,
                "productive": link.productive,
                "tracking_context_id": link.tracking.tracking_context_id,
                "tracking_label": link.tracking.external_label,
                "internal_reference": link.tracking.internal_reference,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        recorded_at=_iso(link.created_at),
    )


def _link_to_row(link: AffiliateLink) -> AffiliateLinkRow:
    return AffiliateLinkRow(
        id=link.affiliate_link_id,
        opportunity_id=link.opportunity_id,
        marketplace=link.marketplace.value,
        original_url=link.original_url,
        affiliate_url=link.affiliate_url,
        generation_method=link.generation_method.value,
        productive=link.productive,
        status=link.status.value,
        tracking_context_id=link.tracking.tracking_context_id,
        tracking_label=link.tracking.external_label or "",
        tracking_brand=link.tracking.brand.value,
        tracking_internal_reference=link.tracking.internal_reference,
        tracking_mapping_version=link.tracking.mapping_version,
        tracking_mapping_hash=link.tracking.mapping_hash,
        correlation_id=link.correlation_id,
        audit_event_id=link.audit_event_id,
        schema_version=link.schema_version,
        created_at=_iso(link.created_at),
    )


def _link_from_row(row: AffiliateLinkRow) -> AffiliateLink:
    tracking = TrackingContext(
        tracking_context_id=row.tracking_context_id,
        opportunity_id=row.opportunity_id,
        marketplace=Marketplace(row.marketplace),
        brand=Brand(row.tracking_brand),
        internal_reference=row.tracking_internal_reference,
        mapping_version=row.tracking_mapping_version,
        mapping_hash=row.tracking_mapping_hash,
        external_label=row.tracking_label,
        configured=bool(row.tracking_label),
    )
    return AffiliateLink(
        affiliate_link_id=row.id,
        opportunity_id=row.opportunity_id,
        marketplace=Marketplace(row.marketplace),
        original_url=row.original_url,
        affiliate_url=row.affiliate_url,
        generation_method=LinkGenerationMethod(row.generation_method),
        tracking=tracking,
        correlation_id=row.correlation_id,
        audit_event_id=row.audit_event_id,
        created_at=datetime.fromisoformat(row.created_at),
        status=AffiliateLinkStatus(row.status),
        schema_version=row.schema_version,
    )


__all__ = [
    "SqlAlchemyAffiliateLinkRepository",
]
