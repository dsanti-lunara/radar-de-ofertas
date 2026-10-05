"""Manual capture orchestration (RDR-011, RDR-012, RDR-014, RDR-015, RDR-021).

The service receives an already-typed :class:`~radar.domain.capture.CaptureIntake`,
sanitizes and validates it, deduplicates the marketplace identity and persists
the whole capture graph in one transaction through a
:class:`CaptureRepository`. The Candidate is queryable through the same port so
the persistence is observable from the public boundary, never through internal
call assertions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from radar.domain.audit import CAPTURE_RECEIVED, AuditEvent
from radar.domain.capture import (
    CAPTURE_SCHEMA_VERSION,
    ENTITY_CANDIDATE,
    ENTITY_MARKETPLACE_PRODUCT,
    ENTITY_OFFER,
    Candidate,
    CandidateState,
    CaptureAggregate,
    CapturedOffer,
    CaptureIntake,
    CaptureSource,
    DiscoveryEvent,
    Evidence,
    IdFactory,
    Marketplace,
    MarketplacePriceHistory,
    MarketplaceProduct,
    NormalizedCapture,
    Offer,
    PriceObservation,
    Product,
    RawCapture,
    build_raw_payload,
    candidate_not_found_error,
    compute_discount_percent,
    default_id_factory,
    marketplace_product_not_found_error,
    normalize_intake,
    to_utc,
)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CaptureRepository(Protocol):
    """Persistence port used by the capture application service."""

    def find_marketplace_product(
        self, marketplace: Marketplace, external_id: str
    ) -> MarketplaceProduct | None: ...

    def find_price_observation(
        self, marketplace_product_id: str, source: CaptureSource, observed_at: datetime
    ) -> PriceObservation | None: ...

    def get_price_history(self, marketplace_product_id: str) -> MarketplacePriceHistory | None: ...

    def save_capture(self, aggregate: CaptureAggregate) -> None: ...

    def get_captured_offer(self, candidate_id: str) -> CapturedOffer | None: ...


@dataclass(slots=True)
class ManualCaptureService:
    """Materialize a manual capture into the domain pipeline."""

    repository: CaptureRepository
    clock: Clock = _utc_now
    id_factory: IdFactory = default_id_factory

    def capture(self, intake: CaptureIntake, *, correlation_id: str) -> CapturedOffer:
        """Validate, deduplicate and persist one capture atomically."""

        normalized = normalize_intake(intake)
        now = to_utc(self.clock())
        captured_at = normalized.captured_at or now
        existing = self.repository.find_marketplace_product(
            normalized.marketplace, normalized.external_id
        )
        aggregate, result = self._materialize(
            normalized,
            existing=existing,
            now=now,
            captured_at=captured_at,
            correlation_id=correlation_id,
        )
        self.repository.save_capture(aggregate)
        return result

    def get_candidate(self, candidate_id: str) -> CapturedOffer:
        """Return a previously captured Candidate or fail with a structured error."""

        captured = self.repository.get_captured_offer(candidate_id)
        if captured is None:
            raise candidate_not_found_error(candidate_id)
        return captured

    def get_price_history(self, marketplace_product_id: str) -> MarketplacePriceHistory:
        """Return the append-only observation series or a structured not-found error."""

        history = self.repository.get_price_history(marketplace_product_id)
        if history is None:
            raise marketplace_product_not_found_error(marketplace_product_id)
        return history

    def _materialize(
        self,
        normalized: NormalizedCapture,
        *,
        existing: MarketplaceProduct | None,
        now: datetime,
        captured_at: datetime,
        correlation_id: str,
    ) -> tuple[CaptureAggregate, CapturedOffer]:
        create_marketplace_product = existing is None
        product: Product | None
        if existing is None:
            product_id = self.id_factory("prd")
            product = Product(
                id=product_id,
                canonical_name=normalized.title or normalized.external_id,
                created_at=now,
                updated_at=now,
            )
            marketplace_product_id = self.id_factory("mkt")
            marketplace_product = MarketplaceProduct(
                id=marketplace_product_id,
                product_id=product_id,
                marketplace=normalized.marketplace,
                external_id=normalized.external_id,
                first_seen_at=captured_at,
                last_seen_at=captured_at,
                url=normalized.url,
                title=normalized.title,
                seller_id=normalized.seller_id,
            )
        else:
            product = None
            product_id = existing.product_id
            marketplace_product_id = existing.id
            marketplace_product = replace(existing, last_seen_at=captured_at)

        offer_id = self.id_factory("off")
        raw_capture_id = self.id_factory("raw")
        discovery_event_id = self.id_factory("disc")
        audit_event_id = self.id_factory("aud")
        candidate_id = self.id_factory("cand")

        offer = Offer(
            id=offer_id,
            marketplace_product_id=marketplace_product_id,
            current_price=normalized.current_price,
            captured_at=captured_at,
            source=normalized.source,
            correlation_id=correlation_id,
            original_price=normalized.original_price,
            discount_percent=compute_discount_percent(
                normalized.current_price, normalized.original_price
            ),
            sales_count=normalized.sales_count,
            seller_id=normalized.seller_id,
            seller_name=normalized.seller_name,
        )
        raw_capture = RawCapture(
            id=raw_capture_id,
            marketplace=normalized.marketplace,
            source=normalized.source,
            payload=build_raw_payload(normalized, captured_at=captured_at),
            captured_at=captured_at,
            correlation_id=correlation_id,
            schema_version=CAPTURE_SCHEMA_VERSION,
            source_url=normalized.url,
        )
        # PriceObservation is append-only and identified by
        # (marketplace_product_id, source, observed_at); a repeated capture with
        # the same identity reuses the existing observation instead of appending
        # a duplicate or inventing a new price (AUT-028).
        existing_observation = self.repository.find_price_observation(
            marketplace_product_id, normalized.source, captured_at
        )
        create_price_observation = existing_observation is None
        price_observation = (
            PriceObservation(
                id=self.id_factory("obs"),
                marketplace_product_id=marketplace_product_id,
                price=normalized.current_price,
                observed_at=captured_at,
                source=normalized.source,
                correlation_id=correlation_id,
                raw_capture_id=raw_capture_id,
                original_price=normalized.original_price,
            )
            if existing_observation is None
            else existing_observation
        )
        evidence = self._build_evidence(
            normalized,
            marketplace_product_id=marketplace_product_id,
            offer_id=offer_id,
            raw_capture_id=raw_capture_id,
            captured_at=captured_at,
        )
        discovery_event = DiscoveryEvent(
            id=discovery_event_id,
            marketplace=normalized.marketplace,
            source=normalized.source,
            external_id=normalized.external_id,
            raw_capture_id=raw_capture_id,
            correlation_id=correlation_id,
            captured_at=captured_at,
        )
        candidate = Candidate(
            id=candidate_id,
            offer_id=offer_id,
            state=CandidateState.NEW,
            correlation_id=correlation_id,
            raw_capture_id=raw_capture_id,
            discovery_event_id=discovery_event_id,
            audit_event_id=audit_event_id,
            created_at=now,
            updated_at=now,
        )
        audit_event = AuditEvent(
            id=audit_event_id,
            event_type=CAPTURE_RECEIVED,
            entity_type=ENTITY_CANDIDATE,
            entity_id=candidate_id,
            source=normalized.source.value,
            correlation_id=correlation_id,
            recorded_at=now,
            payload={
                "marketplace": normalized.marketplace.value,
                "external_id": normalized.external_id,
                "duplicate_identity": not create_marketplace_product,
            },
        )
        aggregate = CaptureAggregate(
            product=product,
            marketplace_product=marketplace_product,
            create_marketplace_product=create_marketplace_product,
            offer=offer,
            price_observation=price_observation,
            create_price_observation=create_price_observation,
            raw_capture=raw_capture,
            evidence=tuple(evidence),
            discovery_event=discovery_event,
            candidate=candidate,
            audit_event=audit_event,
        )
        result = CapturedOffer(
            schema_version=CAPTURE_SCHEMA_VERSION,
            correlation_id=correlation_id,
            candidate_id=candidate_id,
            candidate_state=candidate.state.value,
            offer_id=offer_id,
            product_id=product_id,
            marketplace_product_id=marketplace_product_id,
            raw_capture_id=raw_capture_id,
            discovery_event_id=discovery_event_id,
            audit_event_id=audit_event_id,
            marketplace=normalized.marketplace.value,
            external_id=normalized.external_id,
            source=normalized.source.value,
            title=normalized.title,
            captured_at=captured_at,
            price_observation_id=price_observation.id,
            duplicate_identity=not create_marketplace_product,
        )
        return aggregate, result

    def _build_evidence(
        self,
        normalized: NormalizedCapture,
        *,
        marketplace_product_id: str,
        offer_id: str,
        raw_capture_id: str,
        captured_at: datetime,
    ) -> list[Evidence]:
        facts: list[tuple[str, str, str, str]] = [
            (
                ENTITY_MARKETPLACE_PRODUCT,
                marketplace_product_id,
                "external_id",
                normalized.external_id,
            )
        ]
        if normalized.title is not None:
            facts.append(
                (ENTITY_MARKETPLACE_PRODUCT, marketplace_product_id, "title", normalized.title)
            )
        if normalized.url is not None:
            facts.append(
                (ENTITY_MARKETPLACE_PRODUCT, marketplace_product_id, "url", normalized.url)
            )
        facts.append((ENTITY_OFFER, offer_id, "current_price", str(normalized.current_price)))
        if normalized.original_price is not None:
            facts.append((ENTITY_OFFER, offer_id, "original_price", str(normalized.original_price)))
        if normalized.sales_count is not None:
            facts.append((ENTITY_OFFER, offer_id, "sales_count", str(normalized.sales_count)))
        if normalized.seller_name is not None:
            facts.append((ENTITY_OFFER, offer_id, "seller_name", normalized.seller_name))

        source_type = normalized.source.value
        return [
            Evidence(
                id=self.id_factory("evd"),
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field_name,
                value=value,
                source_type=source_type,
                source_url=normalized.url,
                captured_at=captured_at,
                raw_reference=raw_capture_id,
            )
            for entity_type, entity_id, field_name, value in facts
        ]


__all__ = [
    "CaptureRepository",
    "Clock",
    "ManualCaptureService",
]
