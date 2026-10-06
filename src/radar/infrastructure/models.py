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


class OpportunityRow(Base):
    """Opportunity created only after an approved Candidate (RDR-017, AUT-032).

    The state machine and its allowed transitions live in the domain; this row
    stores the current state and the ``audit_event_id`` of the creation event. The
    ``evaluation_id`` is unique so the same immutable Evaluation can never produce
    two Opportunities (idempotent advance), and ``candidate_id``/``evaluation_id``
    are real foreign keys so an orphan Opportunity is impossible (AUT-233).
    """

    __tablename__ = "opportunity"
    __table_args__ = (
        UniqueConstraint("evaluation_id", name="uq_opportunity_evaluation"),
        Index("ix_opportunity_candidate", "candidate_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("candidate.id"), nullable=False
    )
    evaluation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evaluation.id"), nullable=False
    )
    brand: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class OperationsStateRow(Base):
    """Single durable row with the global operational state (RDR-043, AUT-149).

    ``global_mode`` and ``stop_external_actions`` are the operator commands that
    gate every external side effect; safe reading/diagnostic/recovery never depend
    on this row (AUT-317). The row is upserted atomically with its audit event so
    the command is observable from the public boundary.
    """

    __tablename__ = "operations_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    global_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    stop_external_actions: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class IntegrationHealthRow(Base):
    """Standardized health of one external integration (RDR-044, AUT-139).

    Each integration keeps its own state, so one unhealthy integration isolates
    its own scope instead of the whole node (AUT-315). ``name`` is the primary key
    and the row is upserted atomically with its audit event.
    """

    __tablename__ = "integration_health"
    __table_args__ = (Index("ix_integration_health_state", "state", "updated_at"),)

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class RuntimeStateRow(Base):
    """Single durable runtime/shutdown marker of the Core (RDR-042, AUT-229).

    ``clean_shutdown`` is set only by an explicit clean shutdown, so a startup
    that reads it unset detects an unclean shutdown and runs recovery. The row
    also records the recovery counter and the last recovery/start/shutdown
    instants, so the Recovery Manager is observable from the public boundary.
    """

    __tablename__ = "runtime_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    clean_shutdown: Mapped[bool] = mapped_column(Boolean, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String(40))
    shutdown_at: Mapped[str | None] = mapped_column(String(40))
    last_recovery_at: Mapped[str | None] = mapped_column(String(40))
    recovery_count: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
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


class AIReviewRow(Base):
    """Append-only, versioned editorial AI review (RDR-050, AUT-035/AUT-065).

    SQLite triggers installed by migration ``0013_ai_review`` reject any UPDATE or
    DELETE, so an old review is never overwritten. The row stores the provider and
    model, the knowledge/prompt versions it was produced from, the structured
    decision and the ``allowed_claims``/input snapshot as JSON. Marketplace facts
    are stored sanitized (no HTML, no secrets) and money as decimal strings
    (AUT-203, AUT-232, AUT-299).
    """

    __tablename__ = "ai_review"
    __table_args__ = (Index("ix_ai_review_candidate", "candidate_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("candidate.id"), nullable=False
    )
    evaluation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evaluation.id"), nullable=False
    )
    task: Mapped[str] = mapped_column(String(48), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    knowledge_version: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    editorial_angle: Mapped[str | None] = mapped_column(String(128))
    reason_codes: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_claims: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class HumanReviewRow(Base):
    """Append-only, versioned human review of one Candidate (RDR-060, AUT-035/AUT-036).

    The row stores the snapshotted ``ai_decision`` and the ``human_decision``
    separately (AUT-035) together with the operator ``reason``/``note`` and,
    for an ``EDIT_CONTENT`` decision, the sanitized edited copy. SQLite triggers
    installed by migration ``0018_human_review`` reject UPDATE/DELETE, so the
    decision history is never rewritten, and foreign keys tie the row to its
    Candidate, optional AIReview and audit event (AUT-233). Text is stored
    sanitized (no HTML, no secrets) and timestamps ISO-8601 UTC (AUT-203,
    AUT-299).
    """

    __tablename__ = "human_review"
    __table_args__ = (Index("ix_human_review_candidate", "candidate_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("candidate.id"), nullable=False
    )
    ai_review_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("ai_review.id"), nullable=True
    )
    ai_decision: Mapped[str | None] = mapped_column(String(32))
    human_decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    edited_content: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class AffiliateLinkRow(Base):
    """Independent, auditable affiliate link of one approved Opportunity (RDR-018).

    The row stores the literal ``affiliate_url`` returned by the provider (never
    rewritten by the domain/AI), the generation method, the status and the
    internal tracking context separated from the external label (RDR-070). The
    ``uq_affiliate_link_opportunity_tracking`` unique constraint makes generation
    idempotent for the same Opportunity + label, so a repeated call never
    duplicates the entity (AUT-039, AUT-132). ``opportunity_id`` is a real foreign
    key so an orphan link is impossible (AUT-233).
    """

    __tablename__ = "affiliate_link"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id",
            "tracking_label",
            name="uq_affiliate_link_opportunity_tracking",
        ),
        Index("ix_affiliate_link_opportunity", "opportunity_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("opportunity.id"), nullable=False
    )
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    affiliate_url: Mapped[str] = mapped_column(Text, nullable=False)
    generation_method: Mapped[str] = mapped_column(String(32), nullable=False)
    productive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    tracking_context_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tracking_label: Mapped[str] = mapped_column(String(64), nullable=False)
    tracking_brand: Mapped[str] = mapped_column(String(32), nullable=False)
    tracking_internal_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    tracking_mapping_version: Mapped[str] = mapped_column(String(64), nullable=False)
    tracking_mapping_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ContentGenerationRow(Base):
    """Versioned, auditable content preview of one Opportunity (RDR-019).

    ``generated_content`` (AI copy) and ``final_content`` (renderer output with
    backend price/link/disclosure) are stored separately with their own versions
    (AUT-034, AUT-081, AUT-163). ``facts``/``fact_hash`` snapshot the facts the copy
    depends on, so a later change makes the content ``STALE`` on read without
    mutating the row. ``ai_input_hash`` (RDR-055) records the canonical hash of the
    versioned provider input so an equivalent input reuses the persisted result.
    SQLite triggers installed by migration
    ``0015_content_generation`` reject UPDATE/DELETE, keeping the artifact
    append-only, and foreign keys tie the row to its Opportunity, Candidate and
    audit event (AUT-233). Money is a decimal string and timestamps ISO-8601 UTC
    (AUT-231, AUT-232).
    """

    __tablename__ = "content_generation"
    __table_args__ = (
        Index("ix_content_generation_opportunity", "opportunity_id", "created_at"),
        Index("ix_content_generation_ai_input", "opportunity_id", "ai_input_hash"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("opportunity.id"), nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("candidate.id"), nullable=False
    )
    brand: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    generation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_version: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_content: Mapped[str] = mapped_column(Text, nullable=False)
    final_content: Mapped[str] = mapped_column(Text, nullable=False)
    guards: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[str] = mapped_column(Text, nullable=False)
    fact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ai_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class PublicationRow(Base):
    """Confirmed send of one validated ContentGeneration (RDR-020).

    The row is its own entity (AUT-025, AUT-034): it references the Opportunity,
    the ContentGeneration and the AffiliateLink, and adds the destination, the
    ``external_message_id``, the ``published_price`` and the ``idempotency_key``
    that makes a repeated confirmed send a no-op (AUT-039, AUT-184). The unique
    ``uq_publication_idempotency_key`` constraint enforces that idempotency at the
    database level; foreign keys tie the row to the existing entities (AUT-233).
    Money is a decimal string and timestamps ISO-8601 UTC (AUT-231, AUT-232).
    """

    __tablename__ = "publication"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_publication_idempotency_key"),
        Index("ix_publication_opportunity", "opportunity_id", "created_at"),
        Index("ix_publication_published", "status", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("opportunity.id"), nullable=False
    )
    content_generation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("content_generation.id"), nullable=False
    )
    affiliate_link_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("affiliate_link.id"), nullable=False
    )
    brand: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    destination_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    published_price: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_event.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    published_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PublicationEventRow(Base):
    """Append-only event of a Publication lifecycle (RDR-020, AUT-141).

    SQLite triggers installed by migration ``0017_publication`` reject
    UPDATE/DELETE, so the lifecycle history is never rewritten; ``publication_id``
    is a real foreign key (AUT-233).
    """

    __tablename__ = "publication_event"
    __table_args__ = (Index("ix_publication_event_publication", "publication_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("publication.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
