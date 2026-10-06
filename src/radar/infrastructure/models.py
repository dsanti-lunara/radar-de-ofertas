"""SQLAlchemy mappings for capture, price history, provenance and audit persistence.

Timestamps are stored as ISO-8601 UTC strings (AUT-231) and money as decimal
strings (AUT-232) so SQLite never round-trips a price through binary floating
point. The tables enforce the `marketplace + external_id` identity and the
append-only `price_observation` identity at the database level
(AUT-233, AUT-028, ``docs/03_DOMAIN_MODEL.md``).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class EvaluationRow(Base):
    """Append-only, immutable Evaluation snapshot (RDR-016, AUT-030, AUT-065).

    SQLite triggers installed by migration ``0004_evaluation`` reject any UPDATE
    or DELETE, so old evaluations are never overwritten. The feature snapshot,
    breakdown and scoring versions are stored as JSON so the decision stays
    reproducible and auditable.
    """

    __tablename__ = "evaluation"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("candidate.id"), nullable=False
    )
    brand: Mapped[str] = mapped_column(String(32), nullable=False)
    deal_score: Mapped[str | None] = mapped_column(String(40))
    monetization_score: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[str | None] = mapped_column(String(16))
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    auto_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    passed_rules: Mapped[str] = mapped_column(Text, nullable=False)
    failed_rules: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[str] = mapped_column(Text, nullable=False)
    breakdown: Mapped[str] = mapped_column(Text, nullable=False)
    feature_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    deal_scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    monetization_scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    taxonomy_version: Mapped[str | None] = mapped_column(String(64))
    taxonomy_hash: Mapped[str | None] = mapped_column(String(64))
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class PurchaseSourceDecisionRow(Base):
    """Append-only purchase source decision (RDR-031, AUT-029).

    SQLite triggers installed by migration ``0005_purchase_source_decision``
    reject any UPDATE or DELETE, so a recorded decision is never overwritten. The
    evaluated sources and warnings are stored as JSON and the effective prices as
    decimal strings, so the guardrail stays reproducible and auditable
    (AUT-231, AUT-232).
    """

    __tablename__ = "purchase_source_decision"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("candidate.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    chosen_source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    best_alternative_source_id: Mapped[str | None] = mapped_column(String(128))
    substituted_source_id: Mapped[str | None] = mapped_column(String(128))
    chosen_effective_price: Mapped[str | None] = mapped_column(String(40))
    alternative_effective_price: Mapped[str | None] = mapped_column(String(40))
    difference_percent: Mapped[str | None] = mapped_column(String(40))
    material: Mapped[bool] = mapped_column(Boolean, nullable=False)
    threshold_percent: Mapped[str] = mapped_column(String(40), nullable=False)
    commission_considered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_action: Mapped[str] = mapped_column(String(16), nullable=False)
    sources: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[str] = mapped_column(Text, nullable=False)
    as_of: Mapped[str] = mapped_column(String(40), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class RepostDecisionRow(Base):
    """Append-only repost/dedupe decision (RDR-033, AUT-029, AUT-064).

    SQLite triggers installed by migration ``0006_repost_decision`` reject any
    UPDATE or DELETE, so a recorded decision is never overwritten. The publication
    history used as the baseline, the material changes and the warnings are stored
    as JSON and money as decimal strings, so the guardrail stays reproducible and
    auditable (AUT-231, AUT-232).
    """

    __tablename__ = "repost_decision"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("candidate.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(48), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    material_changes: Mapped[str] = mapped_column(Text, nullable=False)
    publication: Mapped[str | None] = mapped_column(Text)
    current_price: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_price_drop_percent: Mapped[str | None] = mapped_column(String(40))
    cooldown_expires_at: Mapped[str | None] = mapped_column(String(40))
    cooldown_expired: Mapped[bool] = mapped_column(Boolean, nullable=False)
    deal_score: Mapped[str | None] = mapped_column(String(40))
    policy: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[str] = mapped_column(Text, nullable=False)
    as_of: Mapped[str] = mapped_column(String(40), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class JobRow(Base):
    """Durable Workflow queue entry (RDR-034, RDR-035, AUT-121).

    ``priority``, ``available_at``, ``attempts``/``max_attempts`` and
    ``correlation_id`` are persisted; the lease fields (``locked_by``,
    ``locked_at``, ``lease_expires_at``) carry an expiration so a crashed worker
    can be recovered by another one (AUT-133, AUT-140). Job states are separate
    from domain states (AUT-118).
    """

    __tablename__ = "job"
    __table_args__ = (Index("ix_job_claim", "status", "priority", "available_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[str] = mapped_column(String(40), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(128))
    locked_at: Mapped[str | None] = mapped_column(String(40))
    lease_expires_at: Mapped[str | None] = mapped_column(String(40))
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class JobLockRow(Base):
    """Logical lock with expiration (RDR-036, AUT-140)."""

    __tablename__ = "job_lock"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False)
    acquired_at: Mapped[str] = mapped_column(String(40), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(40), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ScheduleRow(Base):
    """Durable Scheduler definition (RDR-039, AUT-117).

    A schedule persists its cadence (``INTERVAL``/``CRON``/``ON_DEMAND``), the Job
    it creates, its operational ``timezone`` and quiet windows, and the
    ``last_tick_at`` cursor used to coalesce missed ticks. The scheduler only
    creates Jobs; the equivalent logical lock lives in ``job_lock`` and is
    consulted before a tick enqueues (AUT-134, AUT-140).
    """

    __tablename__ = "schedule"
    __table_args__ = (
        UniqueConstraint("name", name="uq_schedule_name"),
        Index("ix_schedule_enabled", "enabled", "type"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    job_type: Mapped[str] = mapped_column(String(48), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    cron: Mapped[str | None] = mapped_column(String(128))
    quiet_windows: Mapped[str] = mapped_column(Text, nullable=False)
    lock_name: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    last_tick_at: Mapped[str | None] = mapped_column(String(40))
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class HumanActionRow(Base):
    """Formal human-intervention record (RDR-040, AUT-126, AUT-244).

    A HumanAction references the existing entity (``entity_type``/``entity_id``)
    instead of recreating it, carries the Correlation ID of the pipeline that
    raised it and explains impact/next steps so an operator can act. This ticket
    only creates ``OPEN`` actions; resolution belongs to the Human Actions
    center (RDR-063).
    """

    __tablename__ = "human_action"
    __table_args__ = (Index("ix_human_action_status", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_type: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(48), nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    next_steps: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
