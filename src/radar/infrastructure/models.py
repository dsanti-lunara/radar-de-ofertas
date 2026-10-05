"""SQLAlchemy mappings for capture, price history, provenance and audit persistence.

Timestamps are stored as ISO-8601 UTC strings (AUT-231) and money as decimal
strings (AUT-232) so SQLite never round-trips a price through binary floating
point. The tables enforce the `marketplace + external_id` identity and the
append-only `price_observation` identity at the database level
(AUT-233, AUT-028, ``docs/03_DOMAIN_MODEL.md``).
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for every Radar persistence mapping."""


class ProductRow(Base):
    __tablename__ = "product"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    subcategory: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class MarketplaceProductRow(Base):
    __tablename__ = "marketplace_product"
    __table_args__ = (
        UniqueConstraint("marketplace", "external_id", name="uq_marketplace_product_identity"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("product.id"), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    seller_id: Mapped[str | None] = mapped_column(String(128))
    raw_category: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[str] = mapped_column(String(40), nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String(40), nullable=False)


class OfferRow(Base):
    __tablename__ = "offer"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    marketplace_product_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("marketplace_product.id"), nullable=False
    )
    current_price: Mapped[str] = mapped_column(String(40), nullable=False)
    original_price: Mapped[str | None] = mapped_column(String(40))
    discount_percent: Mapped[str | None] = mapped_column(String(40))
    sales_count: Mapped[int | None] = mapped_column(Integer)
    seller_id: Mapped[str | None] = mapped_column(String(128))
    seller_name: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[float | None] = mapped_column(Float)
    stock: Mapped[int | None] = mapped_column(Integer)
    shipping_cost: Mapped[str | None] = mapped_column(String(40))
    coupon: Mapped[str | None] = mapped_column(Text)
    affiliate_commission: Mapped[str | None] = mapped_column(String(40))
    captured_at: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)


class PriceObservationRow(Base):
    __tablename__ = "price_observation"
    __table_args__ = (
        UniqueConstraint(
            "marketplace_product_id",
            "source",
            "observed_at",
            name="uq_price_observation_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    marketplace_product_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("marketplace_product.id"), nullable=False
    )
    price: Mapped[str] = mapped_column(String(40), nullable=False)
    original_price: Mapped[str | None] = mapped_column(String(40))
    shipping_cost: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[str] = mapped_column(String(40), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_capture_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("raw_capture.id"), nullable=False
    )


class RawCaptureRow(Base):
    __tablename__ = "raw_capture"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[str] = mapped_column(String(40), nullable=False)


class EvidenceRow(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(16))
    raw_reference: Mapped[str | None] = mapped_column(String(64), ForeignKey("raw_capture.id"))


class AuditEventRow(Base):
    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[str] = mapped_column(String(40), nullable=False)


class DiscoveryEventRow(Base):
    __tablename__ = "discovery_event"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_capture_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("raw_capture.id"), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[str] = mapped_column(String(40), nullable=False)


class CandidateRow(Base):
    __tablename__ = "candidate"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    offer_id: Mapped[str] = mapped_column(String(64), ForeignKey("offer.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_capture_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("raw_capture.id"), nullable=False
    )
    discovery_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("discovery_event.id"), nullable=False
    )
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
