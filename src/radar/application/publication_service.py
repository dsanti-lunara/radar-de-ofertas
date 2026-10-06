"""Publication orchestration: ready preview + policy -> Fake send or block.

The service drives the framework-free domain of
:mod:`radar.domain.publication` against persistence, the TKT-17 authorization
gate and the configured :class:`~radar.domain.publication.Publisher` (Fake in
development). It implements the objective of TKT-23 (RDR-020, RDR-072):

* a Publication is only produced for an Opportunity already in
  ``READY_TO_PUBLISH`` whose validated :class:`~radar.domain.content.ContentGeneration`
  is **not stale** (revalidation), with a validated ``AffiliateLink`` (AUT-135);
* the TKT-17 gate (``SHADOW``/``ASSISTED``/compliance/kill switch) and the
  versioned :class:`~radar.domain.publication.PublicationPolicy` (cap/burst/
  cooldown/quiet hours) are evaluated **before** the publisher is called, so a
  blocked request never performs a side effect (AUT-175, GRILL-001);
* a confirmed send is idempotent by ``idempotency_key``: repeating it returns the
  persisted Publication without a second send (AUT-039, AUT-132, AUT-184);
* the Publication, its append-only events and its ``AuditEvent`` are written in
  one transaction (AUT-141).

The service is framework-free (no FastAPI/SQLAlchemy/Chrome). The unknown-result
window (crash after remote acceptance before local commit) belongs to TKT-24 and
``adr/0001-unknown-publication-result.md`` and is deliberately not handled here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from radar.domain.affiliate_link import AffiliateLink
from radar.domain.audit import (
    HUMAN_ACTION_CREATED,
    PUBLICATION_RESOLVED,
    AuditEvent,
)
from radar.domain.audit import (
    PUBLICATION_RESOLUTION_BLOCKED as AUDIT_PUBLICATION_RESOLUTION_BLOCKED,
)
from radar.domain.audit import (
    PUBLICATION_RESULT_UNKNOWN as AUDIT_PUBLICATION_RESULT_UNKNOWN,
)
from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.content import (
    ContentGeneration,
    ContentGenerationStatus,
    content_generation_not_found_error,
)
from radar.domain.human_action import HumanAction, HumanActionType, build_human_action
from radar.domain.knowledge import Channel
from radar.domain.operations import (
    ExternalAction,
    ExternalActionDecision,
    ExternalActionRequest,
)
from radar.domain.opportunity import (
    Opportunity,
    OpportunityState,
    opportunity_not_found_error,
)
from radar.domain.publication import (
    AUDIT_SOURCE_PUBLICATION,
    PUBLICATION_RESOLUTION_BLOCKED,
    PUBLICATION_RESULT_UNKNOWN,
    REASON_REVALIDATION_REQUIRED,
    Publication,
    PublicationError,
    PublicationEvent,
    PublicationEventType,
    PublicationPolicy,
    PublicationResolution,
    PublicationResultUnknown,
    PublicationSendRequest,
    PublicationStatus,
    Publisher,
    build_publication,
    build_suspended_publication,
    evaluate_publication_policy,
    parse_publisher_response,
    prepared_content_hash,
    publication_blocked_error,
    publication_input_invalid_error,
    publication_not_found_error,
    publication_publisher_unavailable_error,
    publication_result_unknown_error,
)
from radar.domain.publication_recovery import (
    UnknownResultEvidence,
    UnknownResultResolution,
    decide_unknown_result,
    resolution_payload,
)
from radar.domain.taxonomy import Brand

#: Publish capability per channel (``docs/08_WORKFLOW_ENGINE.md`` / SDD-09).
PUBLISH_CAPABILITIES: dict[Channel, str] = {
    Channel.TELEGRAM: "PUBLISH_TELEGRAM",
    Channel.WHATSAPP: "PUBLISH_WHATSAPP_GROUP",
}

#: The hard cap window is one day; burst/cooldown are read from the policy.
_HARD_CAP_WINDOW_MINUTES = 24 * 60

#: Maximum length of the caller-supplied idempotency key.
MAX_IDEMPOTENCY_KEY_LENGTH = 256


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OpportunityReader(Protocol):
    """Read port for Opportunities."""

    def get_opportunity(self, opportunity_id: str) -> Opportunity | None: ...


class ContentGenerationReader(Protocol):
    """Read port for ContentGenerations."""

    def get_content_generation(self, content_generation_id: str) -> ContentGeneration | None: ...


class ContentRevalidation(Protocol):
    """Read port that reports whether a ContentGeneration is stale (SDD-08)."""

    def is_stale(self, record: ContentGeneration) -> bool: ...


class AffiliateLinkReader(Protocol):
    """Read port for the validated AffiliateLink of an Opportunity."""

    def find_link_for_opportunity(self, opportunity_id: str) -> AffiliateLink | None: ...


class PublicationAuthorizer(Protocol):
    """The TKT-17 authorization gate consumed before the publisher (RDR-043)."""

    def authorize(
        self, request: ExternalActionRequest, *, correlation_id: str
    ) -> ExternalActionDecision: ...


class PublicationRepository(Protocol):
    """Persistence port for Publications and their append-only events."""

    def save_publication(self, publication: Publication) -> Publication: ...

    def save_suspension(
        self,
        publication: Publication,
        human_action: HumanAction,
        audit_events: tuple[AuditEvent, ...],
    ) -> Publication: ...

    def resolve_publication(
        self,
        publication_id: str,
        *,
        status: PublicationStatus,
        external_message_id: str | None,
        published_at: datetime | None,
        event: PublicationEvent,
        audit_event: AuditEvent,
    ) -> Publication: ...

    def record_audit(self, audit_events: tuple[AuditEvent, ...]) -> None: ...

    def get_publication(self, publication_id: str) -> Publication | None: ...

    def find_by_idempotency_key(self, idempotency_key: str) -> Publication | None: ...

    def find_unknown_for_opportunity(self, opportunity_id: str) -> Publication | None: ...

    def list_publications_for_opportunity(self, opportunity_id: str) -> tuple[Publication, ...]: ...

    def list_published_since(self, since: datetime) -> tuple[Publication, ...]: ...


def _require_clean_text(value: object, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise publication_input_invalid_error("valor deve ser texto", context={"field": field_name})
    cleaned = value.strip()
    if not cleaned:
        raise publication_input_invalid_error(
            "valor não pode ser vazio", context={"field": field_name}
        )
    if len(cleaned) > max_length:
        raise publication_input_invalid_error(
            "valor excede o tamanho máximo",
            context={"field": field_name, "max_length": max_length},
        )
    return cleaned


@dataclass(slots=True)
class PublicationService:
    """Publish a ready preview through the configured publisher or block safely."""

    repository: PublicationRepository
    opportunities: OpportunityReader
    content: ContentGenerationReader
    revalidation: ContentRevalidation
    links: AffiliateLinkReader
    authorizer: PublicationAuthorizer
    policy: PublicationPolicy
    publisher: Publisher
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory

    def publish(
        self,
        opportunity_id: str,
        *,
        content_generation_id: str,
        destination_id: str,
        idempotency_key: str,
        publication_approved: bool,
        correlation_id: str,
    ) -> PublicationResolution:
        """Publish one ready preview or block before the publisher.

        A confirmed ``idempotency_key`` is replayed without a second send; every
        other request is gated by revalidation, authorization/compliance and the
        publication policy before the publisher is called.
        """

        resolved_opportunity = _require_clean_text(
            opportunity_id, field_name="opportunity_id", max_length=64
        )
        resolved_content = _require_clean_text(
            content_generation_id, field_name="content_generation_id", max_length=64
        )
        resolved_destination = _require_clean_text(
            destination_id, field_name="destination_id", max_length=128
        )
        resolved_key = _require_clean_text(
            idempotency_key, field_name="idempotency_key", max_length=MAX_IDEMPOTENCY_KEY_LENGTH
        )
        resolved_correlation = _require_clean_text(
            correlation_id, field_name="correlation_id", max_length=64
        )

        existing = self.repository.find_by_idempotency_key(resolved_key)
        if existing is not None:
            if existing.opportunity_id != resolved_opportunity:
                raise publication_input_invalid_error(
                    "idempotency_key já pertence a outra Opportunity",
                    context={"idempotency_key": resolved_key},
                )
            if existing.status is PublicationStatus.UNKNOWN:
                # A previous send may have been accepted without confirmation: the
                # publication stays suspended and is never auto-resent (ADR 0001).
                raise publication_result_unknown_error(
                    context={
                        "publication_id": existing.publication_id,
                        "idempotency_key": resolved_key,
                        "destination_id": existing.destination_id,
                    }
                )
            if existing.status is not PublicationStatus.PUBLISHED:
                raise publication_input_invalid_error(
                    "idempotency_key já consumido por tentativa resolvida; usar nova chave",
                    context={
                        "idempotency_key": resolved_key,
                        "status": existing.status.value,
                    },
                )
            return PublicationResolution(publication=existing, idempotent_replay=True)

        suspended = self.repository.find_unknown_for_opportunity(resolved_opportunity)
        if suspended is not None:
            # An open unknown-result suspension blocks every new attempt for the
            # opportunity until a sufficient, audited resolution is recorded; a
            # different idempotency key does not bypass the guardrail (GRILL-002).
            raise publication_result_unknown_error(
                context={
                    "publication_id": suspended.publication_id,
                    "idempotency_key": resolved_key,
                    "destination_id": suspended.destination_id,
                    "suspension_status": "OPEN",
                }
            )

        opportunity = self.opportunities.get_opportunity(resolved_opportunity)
        if opportunity is None:
            raise opportunity_not_found_error(resolved_opportunity)
        if opportunity.state is not OpportunityState.READY_TO_PUBLISH:
            raise publication_input_invalid_error(
                "Opportunity não está pronta para publicação",
                context={
                    "opportunity_id": resolved_opportunity,
                    "state": opportunity.state.value,
                    "required_state": OpportunityState.READY_TO_PUBLISH.value,
                },
            )

        content = self.content.get_content_generation(resolved_content)
        if content is None:
            raise content_generation_not_found_error(resolved_content)
        if content.opportunity_id != resolved_opportunity:
            raise publication_input_invalid_error(
                "ContentGeneration não pertence à Opportunity informada",
                context={
                    "content_generation_id": resolved_content,
                    "opportunity_id": resolved_opportunity,
                },
            )
        if content.status is not ContentGenerationStatus.VALIDATED or self.revalidation.is_stale(
            content
        ):
            raise publication_blocked_error(
                reason_code=REASON_REVALIDATION_REQUIRED,
                message="Conteúdo stale exige revalidação antes do envio",
                context={
                    "content_generation_id": resolved_content,
                    "status": content.status.value,
                },
            )

        link = self.links.find_link_for_opportunity(resolved_opportunity)
        if link is None:
            raise publication_input_invalid_error(
                "Opportunity sem AffiliateLink validado não pode publicar",
                context={"opportunity_id": resolved_opportunity},
            )
        if link.affiliate_url != content.rendered.affiliate_url:
            raise publication_input_invalid_error(
                "AffiliateLink divergente do conteúdo renderizado",
                context={"opportunity_id": resolved_opportunity},
            )

        decision = self.authorizer.authorize(
            ExternalActionRequest(
                action=ExternalAction.PUBLISH,
                brand=opportunity.brand,
                channel=content.channel.value,
                capability=PUBLISH_CAPABILITIES[content.channel],
                publication_approved=publication_approved,
            ),
            correlation_id=resolved_correlation,
        )
        if not decision.allowed:
            raise publication_blocked_error(
                reason_code=decision.reason_code,
                message=decision.message,
                context={
                    "action": decision.action.value,
                    "automation_mode": decision.automation_mode.value,
                    "compliance_status": decision.compliance_status.value,
                },
            )

        now = self.clock()
        recent = self.repository.list_published_since(
            self._policy_window_start(now, content.channel)
        )
        policy_decision = evaluate_publication_policy(
            self.policy,
            brand=opportunity.brand,
            channel=content.channel,
            destination_id=resolved_destination,
            now=now,
            publications=recent,
        )
        if not policy_decision.allowed:
            raise publication_blocked_error(
                reason_code=policy_decision.reason_code,
                message=policy_decision.message,
                context={"policy_version": self.policy.policy_version},
            )

        publication_id = str(self.id_factory("pub"))
        send_request = PublicationSendRequest(
            publication_id=publication_id,
            idempotency_key=resolved_key,
            channel=content.channel,
            destination_id=resolved_destination,
            content_text=content.rendered.text,
            affiliate_url=link.affiliate_url,
            correlation_id=resolved_correlation,
        )
        try:
            raw_response = self.publisher.send(send_request)
        except PublicationResultUnknown:
            # The remote may have accepted the message without local confirmation:
            # the result is unknown, so the publication is suspended and a
            # HumanAction opens. No automatic resend ever happens (GRILL-002).
            raise self._suspend_unknown(
                opportunity_id=resolved_opportunity,
                brand=opportunity.brand,
                content_generation_id=resolved_content,
                content=content,
                affiliate_link_id=link.affiliate_link_id,
                destination_id=resolved_destination,
                idempotency_key=resolved_key,
                publication_id=publication_id,
                correlation_id=resolved_correlation,
                now=now,
            ) from None
        except PublicationError:
            raise
        except Exception as exc:
            # An external publisher failure fails closed: no Publication is
            # written and the caller gets a retryable structured error.
            raise publication_publisher_unavailable_error(
                context={"provider": self.publisher.name, "reason": type(exc).__name__}
            ) from exc
        external_message_id = parse_publisher_response(raw_response, provider=self.publisher.name)
        publication = build_publication(
            opportunity_id=resolved_opportunity,
            content_generation_id=resolved_content,
            affiliate_link_id=link.affiliate_link_id,
            brand=opportunity.brand,
            channel=content.channel,
            destination_id=resolved_destination,
            idempotency_key=resolved_key,
            published_price=content.rendered.price,
            external_message_id=external_message_id,
            correlation_id=resolved_correlation,
            audit_event_id=str(self.id_factory("aud")),
            created_at=now,
            published_at=now,
            publication_id=publication_id,
            id_factory=self.id_factory,
        )
        saved = self.repository.save_publication(publication)
        return PublicationResolution(publication=saved, idempotent_replay=False)

    def resolve(
        self,
        publication_id: str,
        *,
        decision: object,
        evidence: Sequence[UnknownResultEvidence],
        correlation_id: str,
    ) -> UnknownResultResolution:
        """Resolve a suspended publication with sufficient, audited evidence.

        A resolution without corroborating evidence fails closed with
        ``RAD-PUB-007`` and leaves the publication suspended: a human
        authorization alone neither proves the previous send failed nor releases a
        new attempt (ADR 0001). A sufficient ``CONFIRM_NOT_SENT`` marks the
        publication ``FAILED``; a new attempt still passes through revalidation and
        every guardrail.
        """

        resolved_id = _require_clean_text(
            publication_id, field_name="publication_id", max_length=64
        )
        resolved_correlation = _require_clean_text(
            correlation_id, field_name="correlation_id", max_length=64
        )
        publication = self.repository.get_publication(resolved_id)
        if publication is None:
            raise publication_not_found_error(resolved_id)
        now = self.clock()
        try:
            resolution = decide_unknown_result(
                publication,
                decision=decision,
                evidence=evidence,
                correlation_id=resolved_correlation,
                now=now,
            )
        except PublicationError as exc:
            if exc.error.code == PUBLICATION_RESOLUTION_BLOCKED:
                self.repository.record_audit(
                    (
                        AuditEvent(
                            id=str(self.id_factory("aud")),
                            event_type=AUDIT_PUBLICATION_RESOLUTION_BLOCKED,
                            entity_type="publication",
                            entity_id=resolved_id,
                            source=AUDIT_SOURCE_PUBLICATION,
                            correlation_id=resolved_correlation,
                            recorded_at=now,
                            payload={
                                "status": publication.status.value,
                                "reason_code": exc.error.context.get("reason_code"),
                            },
                        ),
                    )
                )
            raise
        event = PublicationEvent(
            event_id=str(self.id_factory("pev")),
            publication_id=resolved_id,
            event_type=PublicationEventType.RESOLVED,
            occurred_at=now,
            correlation_id=resolved_correlation,
            payload=dict(resolution_payload(resolution)),
        )
        audit_event = AuditEvent(
            id=str(self.id_factory("aud")),
            event_type=PUBLICATION_RESOLVED,
            entity_type="publication",
            entity_id=resolved_id,
            source=AUDIT_SOURCE_PUBLICATION,
            correlation_id=resolved_correlation,
            recorded_at=now,
            payload={
                "decision": resolution.decision.value,
                "status": resolution.status.value,
                "evidence_types": [item.evidence_type.value for item in resolution.evidence],
            },
        )
        self.repository.resolve_publication(
            resolved_id,
            status=resolution.status,
            external_message_id=resolution.external_message_id,
            published_at=(now if resolution.status is PublicationStatus.PUBLISHED else None),
            event=event,
            audit_event=audit_event,
        )
        return resolution

    def _suspend_unknown(
        self,
        *,
        opportunity_id: str,
        brand: Brand,
        content_generation_id: str,
        content: ContentGeneration,
        affiliate_link_id: str,
        destination_id: str,
        idempotency_key: str,
        publication_id: str,
        correlation_id: str,
        now: datetime,
    ) -> PublicationResultUnknown:
        """Persist the suspension, receipt anchor and HumanAction, then fail closed."""

        content_hash = prepared_content_hash(
            content_text=content.rendered.text,
            affiliate_url=content.rendered.affiliate_url,
            price=content.rendered.price,
            destination_id=destination_id,
            channel=content.channel,
        )
        audit_id = str(self.id_factory("aud"))
        publication = build_suspended_publication(
            opportunity_id=opportunity_id,
            content_generation_id=content_generation_id,
            affiliate_link_id=affiliate_link_id,
            brand=brand,
            channel=content.channel,
            destination_id=destination_id,
            idempotency_key=idempotency_key,
            published_price=content.rendered.price,
            content_hash=content_hash,
            correlation_id=correlation_id,
            audit_event_id=audit_id,
            created_at=now,
            publication_id=publication_id,
            id_factory=self.id_factory,
        )
        human_action = build_human_action(
            action_type=HumanActionType.REVIEW_PUBLICATION,
            entity_type="publication",
            entity_id=publication.publication_id,
            reason="SEND_RESULT_UNKNOWN",
            error_code=PUBLICATION_RESULT_UNKNOWN,
            correlation_id=correlation_id,
            now=now,
            id_factory=self.id_factory,
            impact=(
                "Uma publicação pode ter sido enviada ao destino externo sem "
                "confirmação local; a publicação fica suspensa e o reenvio automático "
                "permanece bloqueado até a revisão."
            ),
            next_steps=(
                "Reunir evidência suficiente (marcador externo, recibo do provider ou "
                "auditoria do destino) e resolver o resultado desconhecido antes de "
                "qualquer nova tentativa; a oferta pode expirar durante a revisão."
            ),
        )
        audit_events = (
            AuditEvent(
                id=audit_id,
                event_type=AUDIT_PUBLICATION_RESULT_UNKNOWN,
                entity_type="publication",
                entity_id=publication.publication_id,
                source=AUDIT_SOURCE_PUBLICATION,
                correlation_id=correlation_id,
                recorded_at=now,
                payload={
                    "destination_id": destination_id,
                    "channel": content.channel.value,
                    "revision": publication.revision,
                    "content_hash": content_hash,
                    "external_message_id": None,
                },
            ),
            AuditEvent(
                id=str(self.id_factory("aud")),
                event_type=HUMAN_ACTION_CREATED,
                entity_type="human_action",
                entity_id=human_action.id,
                source=AUDIT_SOURCE_PUBLICATION,
                correlation_id=correlation_id,
                recorded_at=now,
                payload={
                    "action_type": human_action.action_type.value,
                    "reason": human_action.reason,
                    "entity_type": human_action.entity_type,
                    "entity_id": human_action.entity_id,
                },
            ),
        )
        self.repository.save_suspension(publication, human_action, audit_events)
        return publication_result_unknown_error(
            context={
                "publication_id": publication.publication_id,
                "human_action_id": human_action.id,
                "destination_id": destination_id,
                "content_hash": content_hash,
                "correlation_id": correlation_id,
            }
        )

    def list(self, opportunity_id: str) -> tuple[Publication, ...]:
        """Return the persisted Publications of an Opportunity, oldest first."""

        return self.repository.list_publications_for_opportunity(opportunity_id)

    def get(self, publication_id: str) -> Publication:
        """Return one Publication or fail closed with ``RAD-PUB-002``."""

        record = self.repository.get_publication(publication_id)
        if record is None:
            raise publication_not_found_error(publication_id)
        return record

    def _policy_window_start(self, now: datetime, channel: Channel) -> datetime:
        limits = self.policy.limits_for(channel)
        window = max(
            _HARD_CAP_WINDOW_MINUTES,
            limits.burst_window_minutes,
            limits.cooldown_minutes or 0,
        )
        return now - timedelta(minutes=window)


__all__ = [
    "MAX_IDEMPOTENCY_KEY_LENGTH",
    "PUBLISH_CAPABILITIES",
    "AffiliateLinkReader",
    "ContentGenerationReader",
    "ContentRevalidation",
    "OpportunityReader",
    "PublicationAuthorizer",
    "PublicationRepository",
    "PublicationService",
]
