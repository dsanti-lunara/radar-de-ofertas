"""Unknown send-result suspension and evidence-gated resolution (RDR-128).

``adr/0001-unknown-publication-result.md`` and GRILL-002 require that a send whose
remote result is not confirmed is treated as **unknown**, never as a confirmed
failure: the affected publication is suspended, automatic resend is blocked and a
``HumanAction`` opens for review. Resolving the uncertainty (confirming the send
or releasing a new attempt) requires *sufficient evidence*; a human authorization
alone does not prove the previous send failed.

This framework-free module (no FastAPI/SQLAlchemy/Chrome, AUT-397) owns:

* the versioned receipt evidence accepted for a human resolution;
* the deterministic sufficiency rule that rejects an authorization without
  corroborating evidence;
* :func:`decide_unknown_result`, the pure decision that a suspended
  :class:`~radar.domain.publication.Publication` resolves to ``PUBLISHED`` (send
  confirmed) or ``FAILED`` (send confirmed not to have happened), always recording
  the auditable resolution.

It never calls AI, never creates a link and never sends (AUT-031, AUT-164).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from radar.domain.publication import (
    PUBLICATION_SCHEMA_VERSION,
    Publication,
    PublicationStatus,
    publication_input_invalid_error,
    publication_resolution_blocked_error,
)

#: Error codes shared with ``docs/ERROR_CATALOG.md`` (defined in publication.py).
RESOLUTION_EVIDENCE_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


class UnknownResultEvidenceType(StrEnum):
    """Corroborating evidence accepted to resolve an unknown send result."""

    #: An external message marker/receipt observed at the destination.
    MESSAGE_MARKER = "MESSAGE_MARKER"
    #: A receipt/attestation returned by the publishing provider.
    PROVIDER_RECEIPT = "PROVIDER_RECEIPT"
    #: An operator audit of the destination (message present or absent).
    DESTINATION_AUDIT = "DESTINATION_AUDIT"
    #: A free-form operator note; insufficient on its own by design (ADR 0001).
    OPERATOR_NOTE = "OPERATOR_NOTE"


#: Evidence kinds that prove a send outcome on their own. An ``OPERATOR_NOTE`` or a
#: bare human authorization is deliberately excluded: it does not prove that the
#: previous send failed and must not release a new attempt (ADR 0001).
SUFFICIENT_EVIDENCE_TYPES: frozenset[UnknownResultEvidenceType] = frozenset(
    {
        UnknownResultEvidenceType.MESSAGE_MARKER,
        UnknownResultEvidenceType.PROVIDER_RECEIPT,
        UnknownResultEvidenceType.DESTINATION_AUDIT,
    }
)

#: Maximum length of the free-form evidence reference/source fields.
MAX_EVIDENCE_TEXT_LENGTH = 256


class UnknownResultDecision(StrEnum):
    """Human decision after reviewing the evidence of an unknown result."""

    #: The send is confirmed to have happened (do not resend).
    CONFIRM_SENT = "CONFIRM_SENT"
    #: The send is confirmed not to have happened; a new attempt may be prepared.
    CONFIRM_NOT_SENT = "CONFIRM_NOT_SENT"


@dataclass(frozen=True, slots=True)
class UnknownResultEvidence:
    """One evidence record supporting a human resolution (ADR 0001)."""

    evidence_type: UnknownResultEvidenceType
    reference: str
    source: str | None = None
    observed_at: datetime | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "evidence_type": self.evidence_type.value,
            "reference": self.reference,
            "source": self.source,
            "observed_at": (
                None if self.observed_at is None else _to_utc(self.observed_at).isoformat()
            ),
        }


@dataclass(frozen=True, slots=True)
class UnknownResultResolution:
    """Auditable outcome of resolving a suspended (unknown) publication."""

    publication_id: str
    decision: UnknownResultDecision
    status: PublicationStatus
    external_message_id: str | None
    evidence: tuple[UnknownResultEvidence, ...] = field(default_factory=tuple)
    correlation_id: str = ""
    resolved_at: datetime | None = None
    schema_version: str = PUBLICATION_SCHEMA_VERSION

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "publication_id": self.publication_id,
            "decision": self.decision.value,
            "status": self.status.value,
            "external_message_id": self.external_message_id,
            "evidence": [item.to_contract() for item in self.evidence],
            "correlation_id": self.correlation_id,
            "resolved_at": (
                None if self.resolved_at is None else _to_utc(self.resolved_at).isoformat()
            ),
            "automatic_resend": False,
        }


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


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


def _coerce_evidence_type(value: object) -> UnknownResultEvidenceType:
    if isinstance(value, UnknownResultEvidenceType):
        return value
    try:
        return UnknownResultEvidenceType(str(value))
    except ValueError as exc:
        raise publication_input_invalid_error(
            "evidence_type inválido",
            context={"field": "evidence_type"},
        ) from exc


def build_unknown_result_evidence(
    *,
    evidence_type: object,
    reference: object,
    source: object = None,
    observed_at: datetime | None = None,
) -> UnknownResultEvidence:
    """Build and validate one evidence record, failing closed on missing fields."""

    resolved_type = _coerce_evidence_type(evidence_type)
    resolved_reference = _require_clean_text(
        reference, field_name="reference", max_length=MAX_EVIDENCE_TEXT_LENGTH
    )
    resolved_source = None
    if source is not None:
        resolved_source = _require_clean_text(
            source, field_name="source", max_length=MAX_EVIDENCE_TEXT_LENGTH
        )
    observed = None if observed_at is None else _to_utc(observed_at)
    return UnknownResultEvidence(
        evidence_type=resolved_type,
        reference=resolved_reference,
        source=resolved_source,
        observed_at=observed,
    )


def is_evidence_sufficient(evidence: Sequence[UnknownResultEvidence]) -> bool:
    """True only when at least one corroborating evidence record is present.

    A resolution based solely on ``OPERATOR_NOTE``/human authorization is
    insufficient: it does not prove that the previous send failed (ADR 0001).
    """

    return any(item.evidence_type in SUFFICIENT_EVIDENCE_TYPES for item in evidence)


def decide_unknown_result(
    publication: Publication,
    *,
    decision: object,
    evidence: Sequence[UnknownResultEvidence],
    correlation_id: str,
    now: datetime,
) -> UnknownResultResolution:
    """Resolve a suspended publication, requiring sufficient evidence.

    Fails closed with ``RAD-PUB-007`` when the publication is not suspended or the
    evidence is insufficient, so an authorization without evidence neither proves
    failure nor releases a new attempt. A sufficient ``CONFIRM_NOT_SENT`` marks the
    publication ``FAILED`` (a new attempt may be prepared, still subject to
    revalidation/guardrails); ``CONFIRM_SENT`` marks it ``PUBLISHED``.
    """

    if publication.status is not PublicationStatus.UNKNOWN:
        raise publication_resolution_blocked_error(
            "Publicação não está suspensa por resultado desconhecido",
            context={
                "publication_id": publication.publication_id,
                "status": publication.status.value,
            },
        )
    try:
        resolved_decision = (
            decision
            if isinstance(decision, UnknownResultDecision)
            else UnknownResultDecision(str(decision))
        )
    except ValueError as exc:
        raise publication_input_invalid_error(
            "decision inválido",
            context={"field": "decision"},
        ) from exc

    records = tuple(evidence)
    if not is_evidence_sufficient(records):
        raise publication_resolution_blocked_error(
            "Evidência insuficiente para resolver o resultado desconhecido",
            context={
                "publication_id": publication.publication_id,
                "reason_code": RESOLUTION_EVIDENCE_INSUFFICIENT,
                "required_evidence_types": sorted(item.value for item in SUFFICIENT_EVIDENCE_TYPES),
            },
        )

    if resolved_decision is UnknownResultDecision.CONFIRM_SENT:
        status = PublicationStatus.PUBLISHED
        external_message_id = _sent_marker(records) or publication.external_message_id
    else:
        status = PublicationStatus.FAILED
        external_message_id = None
    return UnknownResultResolution(
        publication_id=publication.publication_id,
        decision=resolved_decision,
        status=status,
        external_message_id=external_message_id,
        evidence=records,
        correlation_id=correlation_id,
        resolved_at=_to_utc(now),
    )


def _sent_marker(evidence: Sequence[UnknownResultEvidence]) -> str | None:
    for item in evidence:
        if item.evidence_type in (
            UnknownResultEvidenceType.MESSAGE_MARKER,
            UnknownResultEvidenceType.PROVIDER_RECEIPT,
        ):
            return item.reference
    return None


def resolution_payload(
    resolution: UnknownResultResolution,
) -> Mapping[str, Any]:
    """Return the append-only ``RESOLVED`` event payload for persistence/audit."""

    return {
        "decision": resolution.decision.value,
        "status": resolution.status.value,
        "external_message_id": resolution.external_message_id,
        "evidence": [item.to_contract() for item in resolution.evidence],
        "resolved_at": (
            None if resolution.resolved_at is None else _to_utc(resolution.resolved_at).isoformat()
        ),
    }


__all__ = [
    "MAX_EVIDENCE_TEXT_LENGTH",
    "RESOLUTION_EVIDENCE_INSUFFICIENT",
    "SUFFICIENT_EVIDENCE_TYPES",
    "UnknownResultDecision",
    "UnknownResultEvidence",
    "UnknownResultEvidenceType",
    "UnknownResultResolution",
    "build_unknown_result_evidence",
    "decide_unknown_result",
    "is_evidence_sufficient",
    "resolution_payload",
]
