"""SQLAlchemy implementation of the capture persistence port.

All writes for one capture happen inside a single transaction, so a rejected or
failing capture never leaves a partial graph (acceptance: "sem escrita
parcial"). The `marketplace + external_id` unique constraint backs the identity
dedupe and a concurrent race fails closed with a retryable structured error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.application.allowed_claims_service import CandidateClaimsContext
from radar.application.demand_service import CandidateDemandContext
from radar.application.price_opportunity_service import CandidatePriceContext
from radar.application.purchase_source_service import CandidatePurchaseContext
from radar.application.repost_service import CandidateRepostContext
from radar.application.seller_quality_service import CandidateSellerContext
from radar.domain.allowed_claims import ClaimPriceFact
from radar.domain.audit import AuditEvent
from radar.domain.capture import (
    Candidate,
    CaptureAggregate,
    CapturedOffer,
    CaptureSource,
    DiscoveryEvent,
    Evidence,
    Marketplace,
    MarketplacePriceHistory,
    MarketplaceProduct,
    Offer,
    PriceHistoryPoint,
    PriceObservation,
    Product,
    RawCapture,
    identity_conflict_error,
)
from radar.domain.price_opportunity import Coupon, PriceHistoryFact
from radar.domain.taxonomy import CandidateCategory
from radar.infrastructure.models import (
    AuditEventRow,
    CandidateRow,
    DiscoveryEventRow,
    EvidenceRow,
    MarketplaceProductRow,
    OfferRow,
    PriceObservationRow,
    ProductRow,
    RawCaptureRow,
)

_IDENTITY_CONSTRAINT = "UNIQUE constraint failed: marketplace_product"


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment)


@dataclass(slots=True)
class SqlAlchemyCaptureRepository:
    """Persist and read capture graphs against the canonical SQLite store."""

    engine: Engine

    def find_marketplace_product(
        self, marketplace: Marketplace, external_id: str
    ) -> MarketplaceProduct | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(MarketplaceProductRow).where(
                    MarketplaceProductRow.marketplace == marketplace.value,
                    MarketplaceProductRow.external_id == external_id,
                )
            ).scalar_one_or_none()
            return None if row is None else _marketplace_product_from_row(row)

    def find_price_observation(
        self, marketplace_product_id: str, source: CaptureSource, observed_at: datetime
    ) -> PriceObservation | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(PriceObservationRow).where(
                    PriceObservationRow.marketplace_product_id == marketplace_product_id,
                    PriceObservationRow.source == source.value,
                    PriceObservationRow.observed_at == _iso(observed_at),
                )
            ).scalar_one_or_none()
            return None if row is None else _price_observation_from_row(row)

    def get_price_history(self, marketplace_product_id: str) -> MarketplacePriceHistory | None:
        with Session(self.engine) as session:
            product = session.get(MarketplaceProductRow, marketplace_product_id)
            if product is None:
                return None
            rows = (
                session.execute(
                    select(PriceObservationRow)
                    .where(PriceObservationRow.marketplace_product_id == marketplace_product_id)
                    .order_by(PriceObservationRow.observed_at, PriceObservationRow.id)
                )
                .scalars()
                .all()
            )
            return MarketplacePriceHistory(
                marketplace_product_id=product.id,
                marketplace=product.marketplace,
                external_id=product.external_id,
                observations=tuple(_price_history_point(row) for row in rows),
            )

    def save_capture(self, aggregate: CaptureAggregate) -> None:
        try:
            with Session(self.engine) as session, session.begin():
                self._insert(session, aggregate)
        except IntegrityError as exc:
            if _IDENTITY_CONSTRAINT in str(exc.orig):
                raise identity_conflict_error(
                    aggregate.marketplace_product.marketplace,
                    aggregate.marketplace_product.external_id,
                ) from exc
            raise

    def get_captured_offer(self, candidate_id: str) -> CapturedOffer | None:
        with Session(self.engine) as session:
            candidate = session.get(CandidateRow, candidate_id)
            if candidate is None:
                return None
            offer = session.get(OfferRow, candidate.offer_id)
            marketplace_product = (
                None
                if offer is None
                else session.get(MarketplaceProductRow, offer.marketplace_product_id)
            )
            raw_capture = session.get(RawCaptureRow, candidate.raw_capture_id)
            discovery_event = session.get(DiscoveryEventRow, candidate.discovery_event_id)
            if offer is None or marketplace_product is None or raw_capture is None:
                return None
            return CapturedOffer(
                schema_version=raw_capture.schema_version,
                correlation_id=raw_capture.correlation_id,
                candidate_id=candidate.id,
                candidate_state=candidate.state,
                offer_id=offer.id,
                product_id=marketplace_product.product_id,
                marketplace_product_id=marketplace_product.id,
                raw_capture_id=raw_capture.id,
                discovery_event_id=(
                    discovery_event.id
                    if discovery_event is not None
                    else candidate.discovery_event_id
                ),
                audit_event_id=candidate.audit_event_id,
                marketplace=marketplace_product.marketplace,
                external_id=marketplace_product.external_id,
                source=(
                    discovery_event.source if discovery_event is not None else raw_capture.source
                ),
                title=marketplace_product.title,
                captured_at=_parse(raw_capture.captured_at),
                duplicate_identity=None,
            )

    def get_candidate_category(self, candidate_id: str) -> CandidateCategory | None:
        """Read the raw category context of a persisted Candidate (RDR-022)."""

        with Session(self.engine) as session:
            candidate = session.get(CandidateRow, candidate_id)
            if candidate is None:
                return None
            offer = session.get(OfferRow, candidate.offer_id)
            if offer is None:
                return None
            marketplace_product = session.get(MarketplaceProductRow, offer.marketplace_product_id)
            if marketplace_product is None:
                return None
            return CandidateCategory(
                candidate_id=candidate.id,
                marketplace_product_id=marketplace_product.id,
                marketplace=marketplace_product.marketplace,
                raw_category=marketplace_product.raw_category,
            )

    def get_candidate_price_context(self, candidate_id: str) -> CandidatePriceContext | None:
        """Read the Offer, confirmed conditions and history of a Candidate (RDR-023).

        Comparable evidence across marketplaces is deliberately ``None`` here:
        product equivalence is owned by RDR-031 (TKT-10), so this ticket reports
        the comparison as an explicit gap instead of inventing a reference.
        """

        with Session(self.engine) as session:
            candidate = session.get(CandidateRow, candidate_id)
            if candidate is None:
                return None
            offer = session.get(OfferRow, candidate.offer_id)
            if offer is None:
                return None
            marketplace_product = session.get(MarketplaceProductRow, offer.marketplace_product_id)
            if marketplace_product is None:
                return None
            rows = (
                session.execute(
                    select(PriceObservationRow)
                    .where(PriceObservationRow.marketplace_product_id == marketplace_product.id)
                    .order_by(PriceObservationRow.observed_at, PriceObservationRow.id)
                )
                .scalars()
                .all()
            )
            coupon = None if offer.coupon is None else Coupon(code=offer.coupon)
            return CandidatePriceContext(
                candidate_id=candidate.id,
                marketplace_product_id=marketplace_product.id,
                current_price=Decimal(offer.current_price),
                captured_at=_parse(offer.captured_at),
                original_price=_optional_decimal(offer.original_price),
                shipping_cost=_optional_decimal(offer.shipping_cost),
                coupon=coupon,
                history=tuple(
                    PriceHistoryFact(
                        price=Decimal(row.price),
                        observed_at=_parse(row.observed_at),
                    )
                    for row in rows
                ),
                comparable=None,
            )

    def get_candidate_seller_context(self, candidate_id: str) -> CandidateSellerContext | None:
        """Read the seller facts persisted for a Candidate (RDR-024).

        Marketplace reputation and official/trusted status are not persisted by
        the manual capture yet, so they are reported as explicit gaps here and
        can only be supplied (validated) at evaluation time.
        """

        with Session(self.engine) as session:
            candidate = session.get(CandidateRow, candidate_id)
            if candidate is None:
                return None
            offer = session.get(OfferRow, candidate.offer_id)
            if offer is None:
                return None
            marketplace_product = session.get(MarketplaceProductRow, offer.marketplace_product_id)
            if marketplace_product is None:
                return None
            return CandidateSellerContext(
                candidate_id=candidate.id,
                marketplace_product_id=marketplace_product.id,
                seller_id=offer.seller_id or marketplace_product.seller_id,
                seller_name=offer.seller_name,
                rating=None if offer.rating is None else Decimal(str(offer.rating)),
                sales_count=offer.sales_count,
                captured_at=_parse(offer.captured_at),
            )

    def get_candidate_demand_context(self, candidate_id: str) -> CandidateDemandContext | None:
        """Read the demand facts persisted for a Candidate (RDR-025).

        Only the raw category and the sales count are persisted by the manual
        capture; the remaining demand signals (rating count, trend, affiliate
        portal signal and badges) are not persisted yet, so they can only be
        supplied (validated) at evaluation time.
        """

        with Session(self.engine) as session:
            candidate = session.get(CandidateRow, candidate_id)
            if candidate is None:
                return None
            offer = session.get(OfferRow, candidate.offer_id)
            if offer is None:
                return None
            marketplace_product = session.get(MarketplaceProductRow, offer.marketplace_product_id)
            if marketplace_product is None:
                return None
            return CandidateDemandContext(
                candidate_id=candidate.id,
                marketplace_product_id=marketplace_product.id,
                marketplace=marketplace_product.marketplace,
                raw_category=marketplace_product.raw_category,
                sales_count=offer.sales_count,
                captured_at=_parse(offer.captured_at),
            )

    def get_candidate_purchase_context(self, candidate_id: str) -> CandidatePurchaseContext | None:
        """Read the chosen Offer facts of a Candidate (RDR-031).

        Product equivalence and comparable conditions are not persisted by the
        manual capture yet, so they are supplied (validated) at decision time and
        reported as explicit gaps when absent.
        """

        with Session(self.engine) as session:
            candidate = session.get(CandidateRow, candidate_id)
            if candidate is None:
                return None
            offer = session.get(OfferRow, candidate.offer_id)
            if offer is None:
                return None
            marketplace_product = session.get(MarketplaceProductRow, offer.marketplace_product_id)
            if marketplace_product is None:
                return None
            coupon = None if offer.coupon is None else Coupon(code=offer.coupon)
            return CandidatePurchaseContext(
                candidate_id=candidate.id,
                marketplace_product_id=marketplace_product.id,
                marketplace=marketplace_product.marketplace,
                current_price=Decimal(offer.current_price),
                captured_at=_parse(offer.captured_at),
                shipping_cost=_optional_decimal(offer.shipping_cost),
                coupon=coupon,
                affiliate_commission=_optional_decimal(offer.affiliate_commission),
            )

    def get_candidate_claims_context(self, candidate_id: str) -> CandidateClaimsContext | None:
        """Read the Offer and append-only history of a Candidate (RDR-032).

        A coupon is only persisted as a raw code by the manual capture, so its
        confirmed state is supplied (validated) at query time and an absent value
        stays an explicit gap. The history carries the provenance of each
        observation so every price claim can point back to its RawCapture.
        """

        with Session(self.engine) as session:
            candidate = session.get(CandidateRow, candidate_id)
            if candidate is None:
                return None
            offer = session.get(OfferRow, candidate.offer_id)
            if offer is None:
                return None
            marketplace_product = session.get(MarketplaceProductRow, offer.marketplace_product_id)
            if marketplace_product is None:
                return None
            rows = (
                session.execute(
                    select(PriceObservationRow)
                    .where(PriceObservationRow.marketplace_product_id == marketplace_product.id)
                    .order_by(PriceObservationRow.observed_at, PriceObservationRow.id)
                )
                .scalars()
                .all()
            )
            coupon = None if offer.coupon is None else Coupon(code=offer.coupon)
            return CandidateClaimsContext(
                candidate_id=candidate.id,
                offer_id=offer.id,
                current_price=Decimal(offer.current_price),
                captured_at=_parse(offer.captured_at),
                source=offer.source,
                correlation_id=candidate.correlation_id,
                raw_capture_id=candidate.raw_capture_id,
                sales_count=offer.sales_count,
                original_price=_optional_decimal(offer.original_price),
                coupon=coupon,
                history=tuple(
                    ClaimPriceFact(
                        observation_id=row.id,
                        price=Decimal(row.price),
                        observed_at=_parse(row.observed_at),
                        source=row.source,
                        correlation_id=row.correlation_id,
                        raw_capture_id=row.raw_capture_id,
                    )
                    for row in rows
                ),
            )

    def get_candidate_repost_context(self, candidate_id: str) -> CandidateRepostContext | None:
        """Read the Offer facts used by the repost guardrail (RDR-033).

        Only the current price and the raw coupon code are persisted by the manual
        capture; comparable conditions and the confirmed coupon state are supplied
        (validated) at decision time and reported as explicit gaps when absent.
        """

        with Session(self.engine) as session:
            candidate = session.get(CandidateRow, candidate_id)
            if candidate is None:
                return None
            offer = session.get(OfferRow, candidate.offer_id)
            if offer is None:
                return None
            marketplace_product = session.get(MarketplaceProductRow, offer.marketplace_product_id)
            if marketplace_product is None:
                return None
            coupon = None if offer.coupon is None else Coupon(code=offer.coupon)
            return CandidateRepostContext(
                candidate_id=candidate.id,
                current_price=Decimal(offer.current_price),
                captured_at=_parse(offer.captured_at),
                correlation_id=candidate.correlation_id,
                raw_capture_id=candidate.raw_capture_id,
                coupon=coupon,
            )

    def _insert(self, session: Session, aggregate: CaptureAggregate) -> None:
        if aggregate.product is not None:
            session.add(_product_to_row(aggregate.product))
            session.flush()
        if aggregate.create_marketplace_product:
            session.add(_marketplace_product_to_row(aggregate.marketplace_product))
            session.flush()
        else:
            session.execute(
                update(MarketplaceProductRow)
                .where(MarketplaceProductRow.id == aggregate.marketplace_product.id)
                .values(
                    last_seen_at=_iso(aggregate.marketplace_product.last_seen_at),
                    raw_category=aggregate.marketplace_product.raw_category,
                )
            )
        session.add(_raw_capture_to_row(aggregate.raw_capture))
        session.flush()
        session.add(_offer_to_row(aggregate.offer))
        session.flush()
        if aggregate.create_price_observation:
            session.add(_price_observation_to_row(aggregate.price_observation))
            session.flush()
        session.add(_audit_event_to_row(aggregate.audit_event))
        session.flush()
        session.add(_discovery_event_to_row(aggregate.discovery_event))
        session.flush()
        session.add_all(_evidence_to_row(item) for item in aggregate.evidence)
        session.flush()
        session.add(_candidate_to_row(aggregate.candidate))


def _product_to_row(product: Product) -> ProductRow:
    return ProductRow(
        id=product.id,
        canonical_name=product.canonical_name,
        brand=product.brand,
        model=product.model,
        category=product.category,
        subcategory=product.subcategory,
        attributes=json.dumps(dict(product.attributes), sort_keys=True),
        created_at=_iso(product.created_at),
        updated_at=_iso(product.updated_at),
    )


def _marketplace_product_to_row(marketplace_product: MarketplaceProduct) -> MarketplaceProductRow:
    return MarketplaceProductRow(
        id=marketplace_product.id,
        product_id=marketplace_product.product_id,
        marketplace=marketplace_product.marketplace.value,
        external_id=marketplace_product.external_id,
        url=marketplace_product.url,
        title=marketplace_product.title,
        seller_id=marketplace_product.seller_id,
        raw_category=marketplace_product.raw_category,
        first_seen_at=_iso(marketplace_product.first_seen_at),
        last_seen_at=_iso(marketplace_product.last_seen_at),
    )


def _marketplace_product_from_row(row: MarketplaceProductRow) -> MarketplaceProduct:
    return MarketplaceProduct(
        id=row.id,
        product_id=row.product_id,
        marketplace=Marketplace(row.marketplace),
        external_id=row.external_id,
        first_seen_at=_parse(row.first_seen_at),
        last_seen_at=_parse(row.last_seen_at),
        url=row.url,
        title=row.title,
        seller_id=row.seller_id,
        raw_category=row.raw_category,
    )


def _optional_decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _price_observation_to_row(observation: PriceObservation) -> PriceObservationRow:
    return PriceObservationRow(
        id=observation.id,
        marketplace_product_id=observation.marketplace_product_id,
        price=str(observation.price),
        original_price=(
            None if observation.original_price is None else str(observation.original_price)
        ),
        shipping_cost=(
            None if observation.shipping_cost is None else str(observation.shipping_cost)
        ),
        source=observation.source.value,
        observed_at=_iso(observation.observed_at),
        correlation_id=observation.correlation_id,
        raw_capture_id=observation.raw_capture_id,
    )


def _price_observation_from_row(row: PriceObservationRow) -> PriceObservation:
    return PriceObservation(
        id=row.id,
        marketplace_product_id=row.marketplace_product_id,
        price=Decimal(row.price),
        observed_at=_parse(row.observed_at),
        source=CaptureSource(row.source),
        correlation_id=row.correlation_id,
        raw_capture_id=row.raw_capture_id,
        original_price=_optional_decimal(row.original_price),
        shipping_cost=_optional_decimal(row.shipping_cost),
    )


def _price_history_point(row: PriceObservationRow) -> PriceHistoryPoint:
    return PriceHistoryPoint(
        price_observation_id=row.id,
        price=Decimal(row.price),
        observed_at=_parse(row.observed_at),
        source=row.source,
        correlation_id=row.correlation_id,
        raw_capture_id=row.raw_capture_id,
        original_price=_optional_decimal(row.original_price),
        shipping_cost=_optional_decimal(row.shipping_cost),
    )


def _offer_to_row(offer: Offer) -> OfferRow:
    return OfferRow(
        id=offer.id,
        marketplace_product_id=offer.marketplace_product_id,
        current_price=str(offer.current_price),
        original_price=None if offer.original_price is None else str(offer.original_price),
        discount_percent=None if offer.discount_percent is None else str(offer.discount_percent),
        sales_count=offer.sales_count,
        seller_id=offer.seller_id,
        seller_name=offer.seller_name,
        rating=offer.rating,
        stock=offer.stock,
        shipping_cost=None if offer.shipping_cost is None else str(offer.shipping_cost),
        coupon=offer.coupon,
        affiliate_commission=(
            None if offer.affiliate_commission is None else str(offer.affiliate_commission)
        ),
        captured_at=_iso(offer.captured_at),
        source=offer.source.value,
        correlation_id=offer.correlation_id,
    )


def _raw_capture_to_row(raw_capture: RawCapture) -> RawCaptureRow:
    return RawCaptureRow(
        id=raw_capture.id,
        marketplace=raw_capture.marketplace.value,
        source=raw_capture.source.value,
        source_url=raw_capture.source_url,
        payload=json.dumps(dict(raw_capture.payload), ensure_ascii=False, sort_keys=True),
        schema_version=raw_capture.schema_version,
        correlation_id=raw_capture.correlation_id,
        captured_at=_iso(raw_capture.captured_at),
    )


def _evidence_to_row(evidence: Evidence) -> EvidenceRow:
    return EvidenceRow(
        id=evidence.id,
        entity_type=evidence.entity_type,
        entity_id=evidence.entity_id,
        field_name=evidence.field_name,
        value=evidence.value,
        source_type=evidence.source_type,
        source_url=evidence.source_url,
        captured_at=_iso(evidence.captured_at),
        confidence=evidence.confidence,
        raw_reference=evidence.raw_reference,
    )


def _audit_event_to_row(audit_event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        id=audit_event.id,
        event_type=audit_event.event_type,
        entity_type=audit_event.entity_type,
        entity_id=audit_event.entity_id,
        source=audit_event.source,
        correlation_id=audit_event.correlation_id,
        payload=json.dumps(dict(audit_event.payload), ensure_ascii=False, sort_keys=True),
        recorded_at=_iso(audit_event.recorded_at),
    )


def _discovery_event_to_row(discovery_event: DiscoveryEvent) -> DiscoveryEventRow:
    return DiscoveryEventRow(
        id=discovery_event.id,
        marketplace=discovery_event.marketplace.value,
        source=discovery_event.source.value,
        external_id=discovery_event.external_id,
        raw_capture_id=discovery_event.raw_capture_id,
        correlation_id=discovery_event.correlation_id,
        captured_at=_iso(discovery_event.captured_at),
    )


def _candidate_to_row(candidate: Candidate) -> CandidateRow:
    return CandidateRow(
        id=candidate.id,
        offer_id=candidate.offer_id,
        state=candidate.state.value,
        correlation_id=candidate.correlation_id,
        raw_capture_id=candidate.raw_capture_id,
        discovery_event_id=candidate.discovery_event_id,
        audit_event_id=candidate.audit_event_id,
        created_at=_iso(candidate.created_at),
        updated_at=_iso(candidate.updated_at),
    )
