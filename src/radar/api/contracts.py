"""HTTP contracts for manual capture (SPEC-01, ``docs/04_DATA_CONTRACTS.md``).

The Pydantic models are the versioned public boundary. They are intentionally
strict (``extra="forbid"``) and reject known sensitive field names anywhere in
the payload before any domain work happens, so a malformed or sensitive capture
never reaches persistence.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from radar.domain.affiliate_link import AFFILIATE_LINK_SCHEMA_VERSION
from radar.domain.ai_review import AI_REVIEW_SCHEMA_VERSION
from radar.domain.capture import (
    CAPTURE_SCHEMA_VERSION,
    CaptureIntake,
    CaptureSource,
    Marketplace,
    find_sensitive_fields,
)
from radar.domain.content import CONTENT_SCHEMA_VERSION
from radar.domain.evaluation import EVALUATION_SCHEMA_VERSION
from radar.domain.job import DEFAULT_MAX_ATTEMPTS, JOB_SCHEMA_VERSION
from radar.domain.knowledge import Channel
from radar.domain.operations import (
    OPERATIONS_SCHEMA_VERSION,
    ExternalAction,
    GlobalMode,
    IntegrationState,
)
from radar.domain.purchase_source import PURCHASE_SOURCE_SCHEMA_VERSION
from radar.domain.recovery import RECOVERY_SCHEMA_VERSION
from radar.domain.repost import REPOST_SCHEMA_VERSION, RepostEvidenceType
from radar.domain.schedule import SCHEDULE_SCHEMA_VERSION
from radar.domain.taxonomy import Brand
from radar.domain.workflow import WORKFLOW_SCHEMA_VERSION

#: Request/response header carrying the pipeline Correlation ID (AUT-040).
CORRELATION_HEADER = "X-Correlation-ID"

#: Custom validator type used to classify a rejected sensitive field.
SENSITIVE_FIELD_ERROR_TYPE = "radar_sensitive_field"


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaptureSellerContract(_StrictContract):
    name: str | None = Field(default=None, max_length=512)
    id: str | None = Field(default=None, max_length=128)


class CaptureProductContract(_StrictContract):
    external_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2048)
    category: str | None = Field(default=None, max_length=512)


class CaptureOfferContract(_StrictContract):
    current_price: str | int
    original_price: str | int | None = None
    sales_count: int | None = Field(default=None, ge=0)
    seller: CaptureSellerContract | None = None

    @field_validator("current_price", "original_price", mode="before")
    @classmethod
    def _reject_boolean_money(cls, value: object) -> object:
        # ``bool`` is a subclass of ``int``; a JSON ``true`` must never become a price.
        if isinstance(value, bool):
            raise ValueError("Valores monetários devem ser strings decimais")
        return value


class ManualCaptureContract(_StrictContract):
    """Versioned ``ManualCapture`` input received by the public boundary."""

    schema_version: str = CAPTURE_SCHEMA_VERSION
    marketplace: Marketplace
    source: CaptureSource
    product: CaptureProductContract
    offer: CaptureOfferContract
    captured_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_fields(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            hits = find_sensitive_fields(data)
            if hits:
                raise PydanticCustomError(
                    SENSITIVE_FIELD_ERROR_TYPE,
                    "Campos sensíveis não são aceitos na captura",
                    {"fields": list(hits)},
                )
        return data

    def to_intake(self) -> CaptureIntake:
        """Map the validated contract to the framework-free domain intake."""

        seller = self.offer.seller
        return CaptureIntake(
            marketplace=self.marketplace,
            source=self.source,
            external_id=self.product.external_id,
            current_price=self.offer.current_price,
            original_price=self.offer.original_price,
            title=self.product.title,
            url=self.product.url,
            category=self.product.category,
            sales_count=self.offer.sales_count,
            seller_name=seller.name if seller is not None else None,
            seller_id=seller.id if seller is not None else None,
            captured_at=self.captured_at,
            schema_version=self.schema_version,
        )


class EvaluationDealContract(_StrictContract):
    """Normalized Deal components produced by the dependent tickets.

    Brand Fit is resolved from the active taxonomy, not supplied here, so a
    caller cannot bypass the approved calibration.
    """

    price_opportunity: int | None = None
    seller_quality: int | None = None
    demand: int | None = None


class EvaluationMonetizationContract(_StrictContract):
    """Monetization components (``docs/05_SCORING_ENGINE.md``)."""

    estimated_commission: int | None = None
    effective_commission_percent: int | None = None
    conversion_evidence: int | None = None
    extra_commission: int | None = None


class EvaluationConfidenceContract(_StrictContract):
    """Confidence components (``docs/05_SCORING_ENGINE.md``)."""

    source_reliability: int | None = None
    freshness: int | None = None
    completeness: int | None = None
    price_history_depth: int | None = None
    cross_validation: int | None = None


class EvaluationRequestContract(_StrictContract):
    """Versioned input received by the public Evaluation boundary (RDR-016)."""

    schema_version: str = EVALUATION_SCHEMA_VERSION
    brand: Brand
    deal: EvaluationDealContract
    monetization: EvaluationMonetizationContract = Field(
        default_factory=EvaluationMonetizationContract
    )
    confidence: EvaluationConfidenceContract = Field(default_factory=EvaluationConfidenceContract)
    hard_rules: list[str] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != EVALUATION_SCHEMA_VERSION:
            raise ValueError("schema_version de Evaluation não suportada")
        return value


class PurchaseSourceAlternativeContract(_StrictContract):
    """One reliable alternative source compared with the affiliate source."""

    source_id: str = Field(min_length=1, max_length=128)
    marketplace: Marketplace | None = None
    url: str | None = Field(default=None, max_length=2048)
    price: str | int
    shipping_cost: str | int | None = None
    coupon_state: str | None = None
    coupon_amount: str | int | None = None
    coupon_code: str | None = Field(default=None, max_length=128)
    product_equivalence_id: str | None = Field(default=None, max_length=128)
    conditions: dict[str, str] = Field(default_factory=dict)
    affiliate_commission: str | int | None = None

    @field_validator(
        "price",
        "shipping_cost",
        "coupon_amount",
        "affiliate_commission",
        mode="before",
    )
    @classmethod
    def _reject_boolean_money(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Valores monetários devem ser strings decimais")
        return value


class PurchaseSourceRequestContract(_StrictContract):
    """Versioned input received by the Purchase Source boundary (RDR-031)."""

    schema_version: str = PURCHASE_SOURCE_SCHEMA_VERSION
    product_equivalence_id: str | None = Field(default=None, max_length=128)
    conditions: dict[str, str] = Field(default_factory=dict)
    shipping_cost: str | int | None = None
    coupon_state: str | None = None
    coupon_amount: str | int | None = None
    coupon_code: str | None = Field(default=None, max_length=128)
    affiliate_commission: str | int | None = None
    alternatives: list[PurchaseSourceAlternativeContract] = Field(default_factory=list)

    @field_validator(
        "shipping_cost",
        "coupon_amount",
        "affiliate_commission",
        mode="before",
    )
    @classmethod
    def _reject_boolean_money(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Valores monetários devem ser strings decimais")
        return value

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != PURCHASE_SOURCE_SCHEMA_VERSION:
            raise ValueError("schema_version de Purchase Source não suportada")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_fields(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            hits = find_sensitive_fields(data)
            if hits:
                raise PydanticCustomError(
                    SENSITIVE_FIELD_ERROR_TYPE,
                    "Campos sensíveis não são aceitos na comparação",
                    {"fields": list(hits)},
                )
        return data


class RepostPublicationContract(_StrictContract):
    """One prior publication supplied as (fake) publication history (RDR-033)."""

    publication_id: str | None = Field(default=None, max_length=128)
    published_at: datetime
    price: str | int
    coupon_state: str | None = None
    coupon_amount: str | int | None = None
    coupon_code: str | None = Field(default=None, max_length=128)
    conditions: dict[str, str] = Field(default_factory=dict)

    @field_validator("price", "coupon_amount", mode="before")
    @classmethod
    def _reject_boolean_money(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Valores monetários devem ser strings decimais")
        return value


class RepostEvidenceContract(_StrictContract):
    """Evidence that sustains a material coupon/condition (AUT-029)."""

    evidence_type: RepostEvidenceType
    reference_id: str = Field(min_length=1, max_length=128)
    field: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=512)
    source: str = Field(default="repost_input", min_length=1, max_length=32)


class RepostRequestContract(_StrictContract):
    """Versioned input received by the repost boundary (RDR-033)."""

    schema_version: str = REPOST_SCHEMA_VERSION
    coupon_state: str | None = None
    coupon_amount: str | int | None = None
    coupon_code: str | None = Field(default=None, max_length=128)
    conditions: dict[str, str] = Field(default_factory=dict)
    publications: list[RepostPublicationContract] = Field(default_factory=list)
    evidence: list[RepostEvidenceContract] = Field(default_factory=list)

    @field_validator("coupon_amount", mode="before")
    @classmethod
    def _reject_boolean_money(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Valores monetários devem ser strings decimais")
        return value

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != REPOST_SCHEMA_VERSION:
            raise ValueError("schema_version de repost não suportada")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_fields(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            hits = find_sensitive_fields(data)
            if hits:
                raise PydanticCustomError(
                    SENSITIVE_FIELD_ERROR_TYPE,
                    "Campos sensíveis não são aceitos no guardrail de repost",
                    {"fields": list(hits)},
                )
        return data


class JobEnqueueContract(_StrictContract):
    """Versioned input to enqueue a Job (RDR-034).

    ``type`` stays a plain string so the domain owns the Job-type validation and
    can reject a domain state (e.g. ``NEW``) with ``RAD-WF-006`` instead of
    silently coercing it into a Job state (AUT-118).
    """

    schema_version: str = JOB_SCHEMA_VERSION
    type: str = Field(min_length=1, max_length=48)
    entity_type: str | None = Field(default=None, max_length=32)
    entity_id: str | None = Field(default=None, max_length=64)
    priority: int = Field(default=0, strict=True)
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1, strict=True)
    available_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_fields(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            hits = find_sensitive_fields(data)
            if hits:
                raise PydanticCustomError(
                    SENSITIVE_FIELD_ERROR_TYPE,
                    "Campos sensíveis não são aceitos no job",
                    {"fields": list(hits)},
                )
        return data


class JobClaimContract(_StrictContract):
    """Versioned input to claim a Job lease (RDR-035)."""

    schema_version: str = JOB_SCHEMA_VERSION
    worker_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int | None = Field(default=None, gt=0, strict=True)


class JobWorkerContract(_StrictContract):
    """Versioned input carrying the worker id for a Job transition."""

    schema_version: str = JOB_SCHEMA_VERSION
    worker_id: str = Field(min_length=1, max_length=128)


class JobFailContract(_StrictContract):
    """Versioned input to report a Job failure (RDR-037/038).

    The failure class is derived from the structured ``error_code`` by the domain,
    so a caller cannot report an authentication/permanent error as retryable.
    """

    schema_version: str = JOB_SCHEMA_VERSION
    worker_id: str = Field(min_length=1, max_length=128)
    error_code: str = Field(min_length=1, max_length=64)


class LockAcquireContract(_StrictContract):
    """Versioned input to acquire a logical lock (RDR-036)."""

    schema_version: str = JOB_SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=128)
    owner: str = Field(min_length=1, max_length=128)
    ttl_seconds: int | None = Field(default=None, gt=0, strict=True)


class QuietWindowContract(_StrictContract):
    """One recurring local-time quiet window (RDR-039, AUT-143)."""

    start: str = Field(min_length=5, max_length=5)
    end: str = Field(min_length=5, max_length=5)
    days: list[int] = Field(default_factory=list)


class ScheduleCreateContract(_StrictContract):
    """Versioned input to create a Schedule (RDR-039).

    ``type`` and ``job_type`` stay plain strings so the domain owns the enum
    validation and rejects an unknown cadence/domain state with ``RAD-WF-012``.
    """

    schema_version: str = SCHEDULE_SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=16)
    job_type: str = Field(min_length=1, max_length=48)
    priority: int = Field(default=0, strict=True)
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1, strict=True)
    enabled: bool = True
    timezone: str | None = Field(default=None, max_length=64)
    interval_seconds: int | None = Field(default=None, gt=0, strict=True)
    cron: str | None = Field(default=None, max_length=128)
    quiet_windows: list[QuietWindowContract] = Field(default_factory=list)
    lock_name: str | None = Field(default=None, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    entity_type: str | None = Field(default=None, max_length=32)
    entity_id: str | None = Field(default=None, max_length=64)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != SCHEDULE_SCHEMA_VERSION:
            raise ValueError("schema_version de schedule não suportada")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_fields(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            hits = find_sensitive_fields(data)
            if hits:
                raise PydanticCustomError(
                    SENSITIVE_FIELD_ERROR_TYPE,
                    "Campos sensíveis não são aceitos no schedule",
                    {"fields": list(hits)},
                )
        return data


class OpportunityAdvanceContract(_StrictContract):
    """Versioned input to advance a Candidate to an Opportunity (RDR-017)."""

    schema_version: str = WORKFLOW_SCHEMA_VERSION
    priority: int = Field(default=0, strict=True)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != WORKFLOW_SCHEMA_VERSION:
            raise ValueError("schema_version de Opportunity não suportada")
        return value


class OpportunityTransitionContract(_StrictContract):
    """Versioned input to transition an Opportunity (RDR-041).

    ``target_state`` stays a plain string so the domain owns the state-machine
    validation and rejects an unknown state with ``RAD-WF-016`` instead of
    coercing it silently.
    """

    schema_version: str = WORKFLOW_SCHEMA_VERSION
    target_state: str = Field(min_length=1, max_length=24)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != WORKFLOW_SCHEMA_VERSION:
            raise ValueError("schema_version de Opportunity não suportada")
        return value


class OperationsModeContract(_StrictContract):
    """Versioned input to change the global operational mode (RDR-043)."""

    schema_version: str = OPERATIONS_SCHEMA_VERSION
    mode: GlobalMode
    reason: str | None = Field(default=None, max_length=512)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != OPERATIONS_SCHEMA_VERSION:
            raise ValueError("schema_version de operações não suportada")
        return value


class StopExternalActionsContract(_StrictContract):
    """Versioned input to engage/release the kill switch (RDR-043)."""

    schema_version: str = OPERATIONS_SCHEMA_VERSION
    reason: str | None = Field(default=None, max_length=512)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != OPERATIONS_SCHEMA_VERSION:
            raise ValueError("schema_version de operações não suportada")
        return value


class ExternalActionAuthorizationContract(_StrictContract):
    """Versioned input to authorize or block one external action (RDR-043)."""

    schema_version: str = OPERATIONS_SCHEMA_VERSION
    action: ExternalAction
    brand: Brand | None = None
    marketplace: str | None = Field(default=None, max_length=32)
    channel: str | None = Field(default=None, max_length=32)
    capability: str | None = Field(default=None, max_length=64)
    integration: str | None = Field(default=None, max_length=32)
    publication_approved: bool = False

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != OPERATIONS_SCHEMA_VERSION:
            raise ValueError("schema_version de operações não suportada")
        return value


class IntegrationHealthContract(_StrictContract):
    """Versioned input to update one integration health (RDR-044)."""

    schema_version: str = OPERATIONS_SCHEMA_VERSION
    state: IntegrationState
    summary: str | None = Field(default=None, max_length=512)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != OPERATIONS_SCHEMA_VERSION:
            raise ValueError("schema_version de operações não suportada")
        return value


class RecoveryRunContract(_StrictContract):
    """Versioned input to run the startup Recovery Manager (RDR-042).

    ``trigger`` stays a plain string so the domain owns the trigger validation
    and rejects an unknown origin with ``RAD-WF-019``.
    """

    schema_version: str = RECOVERY_SCHEMA_VERSION
    trigger: str | None = Field(default=None, max_length=16)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != RECOVERY_SCHEMA_VERSION:
            raise ValueError("schema_version de recovery não suportada")
        return value


class RecoveryShutdownContract(_StrictContract):
    """Versioned input to record a clean shutdown (RDR-042, AUT-228)."""

    schema_version: str = RECOVERY_SCHEMA_VERSION

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != RECOVERY_SCHEMA_VERSION:
            raise ValueError("schema_version de recovery não suportada")
        return value


class AffiliateLinkRequestContract(_StrictContract):
    """Versioned input to generate an AffiliateLink (RDR-018, RDR-070).

    Only the internal tracking reference may be supplied: the external
    ``tracking_label`` is resolved from the versioned mapping, so a caller can
    never inject or override a marketplace label.
    """

    schema_version: str = AFFILIATE_LINK_SCHEMA_VERSION
    tracking_reference: str | None = Field(default=None, max_length=128)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != AFFILIATE_LINK_SCHEMA_VERSION:
            raise ValueError("schema_version de AffiliateLink não suportada")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_fields(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            hits = find_sensitive_fields(data)
            if hits:
                raise PydanticCustomError(
                    SENSITIVE_FIELD_ERROR_TYPE,
                    "Campos sensíveis não são aceitos na geração de link",
                    {"fields": list(hits)},
                )
        return data


class AIReviewRequestContract(_StrictContract):
    """Versioned input to run an Editorial Review (RDR-050).

    Only the target channel is supplied by the caller: the reviewed facts, the
    Immutable Evaluation and the ``allowed_claims`` are read from persistence, so
    a caller can never inject a claim or steer the AI with unverified content.
    """

    schema_version: str = AI_REVIEW_SCHEMA_VERSION
    channel: Channel

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != AI_REVIEW_SCHEMA_VERSION:
            raise ValueError("schema_version de AIReview não suportada")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_fields(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            hits = find_sensitive_fields(data)
            if hits:
                raise PydanticCustomError(
                    SENSITIVE_FIELD_ERROR_TYPE,
                    "Campos sensíveis não são aceitos no Editorial Review",
                    {"fields": list(hits)},
                )
        return data


class ContentGenerationRequestContract(_StrictContract):
    """Versioned input to generate a content preview (RDR-051).

    Only the target channel is supplied by the caller: the facts, the immutable
    Evaluation, the ``allowed_claims`` and the validated AffiliateLink are read
    from persistence, so a caller can never inject a price, claim or URL.
    """

    schema_version: str = CONTENT_SCHEMA_VERSION
    channel: Channel

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != CONTENT_SCHEMA_VERSION:
            raise ValueError("schema_version de ContentGeneration não suportada")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_fields(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            hits = find_sensitive_fields(data)
            if hits:
                raise PydanticCustomError(
                    SENSITIVE_FIELD_ERROR_TYPE,
                    "Campos sensíveis não são aceitos na geração de conteúdo",
                    {"fields": list(hits)},
                )
        return data
