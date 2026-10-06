"""Auditable human review of a Candidate (RDR-060, AUT-035, AUT-036, GRILL-001).

``docs/03_DOMAIN_MODEL.md`` defines ``HumanReview`` as the artifact used in
Shadow/Assisted that stores the ``ai_decision``, the ``human_decision``, the
``reason`` and ``reviewed_at`` **separately** from the ``AIReview`` (AUT-035).
This module is the framework-free core of that contract:

* it snapshots the AI editorial decision (when there is one) together with the
  human decision, so a later AI review can never rewrite what the operator saw;
* it accepts the three review actions the UI exposes (``APPROVE``, ``REJECT``
  and ``EDIT_CONTENT``) and never performs a commercial send itself. Approving a
  Candidate is **not** a publication approval (GRILL-001, CONTEXT.md);
* the record is immutable/append-only: a new review is always a new row, so the
  decision history stays auditable (AUT-010, AUT-030).

No AI, HTTP, SQLAlchemy or browser code lives here (AUT-397).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from radar.domain.capture import (
    IdFactory,
    default_id_factory,
    sanitize_single_line,
)
from radar.domain.errors import RadarError, RadarException

#: Version of the public HumanReview contract (``docs/04_DATA_CONTRACTS.md``).
HUMAN_REVIEW_SCHEMA_VERSION = "1.0"

#: Entity type and audit provenance recorded for a HumanReview.
ENTITY_HUMAN_REVIEW = "human_review"
AUDIT_SOURCE_HUMAN_REVIEW = "ui"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
HUMAN_REVIEW_INPUT_INVALID = "RAD-UI-001"
HUMAN_REVIEW_NOT_FOUND = "RAD-UI-002"
REVIEW_CANDIDATE_NOT_FOUND = "RAD-UI-003"

#: Maximum length of the free-form review fields.
MAX_REVIEW_TEXT_LENGTH = 512

_HTML_TAG = re.compile(r"<[^>]*>")


class HumanDecision(StrEnum):
    """Human review actions offered by the Control Center (RDR-060)."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EDIT_CONTENT = "EDIT_CONTENT"


class HumanReviewError(RadarException):
    """Base error raised when a HumanReview operation cannot be completed."""


def human_review_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> HumanReviewError:
    """Build the structured ``RAD-UI-001`` error for an invalid review input."""

    return HumanReviewError(
        RadarError(
            code=HUMAN_REVIEW_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir a decisão da review e enviar novamente",
            context=dict(context or {}),
        )
    )


def human_review_not_found_error(human_review_id: str) -> HumanReviewError:
    """Build the structured ``RAD-UI-002`` error for a missing HumanReview."""

    return HumanReviewError(
        RadarError(
            code=HUMAN_REVIEW_NOT_FOUND,
            message="HumanReview não encontrada",
            retryable=False,
            action="Verificar o human_review_id informado",
            context={"human_review_id": human_review_id},
        )
    )


def review_candidate_not_found_error(candidate_id: str) -> HumanReviewError:
    """Build the structured ``RAD-UI-003`` error for a missing Candidate."""

    return HumanReviewError(
        RadarError(
            code=REVIEW_CANDIDATE_NOT_FOUND,
            message="Candidate da review não encontrado",
            retryable=False,
            action="Verificar o candidate_id informado no Inbox",
            context={"candidate_id": candidate_id},
        )
    )


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _require_clean_text(value: object, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise human_review_input_invalid_error(
            "valor deve ser texto", context={"field": field_name}
        )
    cleaned = sanitize_single_line(value)
    if not cleaned:
        raise human_review_input_invalid_error(
            "valor não pode ser vazio", context={"field": field_name}
        )
    if len(cleaned) > max_length:
        raise human_review_input_invalid_error(
            "valor excede o tamanho máximo",
            context={"field": field_name, "max_length": max_length},
        )
    return cleaned


def _require_clean_content(value: object, *, field_name: str, max_length: int) -> str:
    """Sanitize operator-edited copy: strip HTML tags and control characters.

    Marketplace/AI free text is inert data, so the edited preview never keeps an
    HTML/script payload (AUT-203, AUT-299); the result is compared to a plain
    string only.
    """

    if not isinstance(value, str):
        raise human_review_input_invalid_error(
            "valor deve ser texto", context={"field": field_name}
        )
    cleaned = sanitize_single_line(_HTML_TAG.sub("", value))
    if not cleaned:
        raise human_review_input_invalid_error(
            "valor não pode ser vazio", context={"field": field_name}
        )
    if len(cleaned) > max_length:
        raise human_review_input_invalid_error(
            "valor excede o tamanho máximo",
            context={"field": field_name, "max_length": max_length},
        )
    return cleaned


def _coerce_human_decision(value: object) -> HumanDecision:
    if isinstance(value, HumanDecision):
        return value
    try:
        return HumanDecision(str(value))
    except ValueError as exc:
        raise human_review_input_invalid_error(
            "human_decision inválida",
            context={
                "field": "human_decision",
                "allowed": [decision.value for decision in HumanDecision],
            },
        ) from exc


@dataclass(frozen=True, slots=True)
class EditedContent:
    """Sanitized human-edited copy kept separate from the AI-generated content.

    ``docs/11_OPERATIONS_AND_UI.md`` requires the review to keep generated and
    final content apart; this snapshot stores only the operator's inert text (no
    HTML, no link) so an edit can never steer a side effect silently.
    """

    headline: str
    body: str
    cta: str

    def to_contract(self) -> dict[str, str]:
        return {"headline": self.headline, "body": self.body, "cta": self.cta}


@dataclass(frozen=True, slots=True)
class HumanReview:
    """Immutable, auditable human decision over one Candidate (AUT-035/AUT-036)."""

    human_review_id: str
    candidate_id: str
    ai_review_id: str | None
    ai_decision: str | None
    human_decision: HumanDecision
    reason: str
    note: str | None
    edited_content: EditedContent | None
    correlation_id: str
    audit_event_id: str
    reviewed_at: datetime
    schema_version: str = HUMAN_REVIEW_SCHEMA_VERSION

    @property
    def is_candidate_approval(self) -> bool:
        """True when the operator accepted the Candidate as an Opportunity."""

        return self.human_decision is HumanDecision.APPROVE

    @property
    def publication_authorized(self) -> bool:
        """Candidate approval never authorizes a commercial send (GRILL-001)."""

        return False

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": "RECORDED",
            "human_review_id": self.human_review_id,
            "candidate_id": self.candidate_id,
            "ai_review_id": self.ai_review_id,
            "ai_decision": self.ai_decision,
            "human_decision": self.human_decision.value,
            "reason": self.reason,
            "note": self.note,
            "edited_content": (
                None if self.edited_content is None else self.edited_content.to_contract()
            ),
            "decision_matches_ai": (
                None if self.ai_decision is None else self.ai_decision == self.human_decision.value
            ),
            "publication_authorized": self.publication_authorized,
            "reviewed_at": _to_utc(self.reviewed_at).isoformat(),
            "correlation_id": self.correlation_id,
            "audit_event_id": self.audit_event_id,
        }


def build_edited_content(value: object) -> EditedContent:
    """Validate the ``EDIT_CONTENT`` payload, failing closed on any bad field."""

    if not isinstance(value, Mapping):
        raise human_review_input_invalid_error(
            "edited_content deve ser um objeto",
            context={"field": "edited_content"},
        )
    return EditedContent(
        headline=_require_clean_content(
            value.get("headline"),
            field_name="edited_content.headline",
            max_length=MAX_REVIEW_TEXT_LENGTH,
        ),
        body=_require_clean_content(
            value.get("body"), field_name="edited_content.body", max_length=MAX_REVIEW_TEXT_LENGTH
        ),
        cta=_require_clean_content(
            value.get("cta"), field_name="edited_content.cta", max_length=MAX_REVIEW_TEXT_LENGTH
        ),
    )


def build_human_review(
    *,
    candidate_id: object,
    human_decision: object,
    reason: object,
    correlation_id: object,
    now: datetime,
    ai_review_id: object = None,
    ai_decision: object = None,
    note: object = None,
    edited_content: object = None,
    human_review_id: object | None = None,
    schema_version: object = HUMAN_REVIEW_SCHEMA_VERSION,
    id_factory: IdFactory = default_id_factory,
) -> HumanReview:
    """Build and validate a ``HumanReview`` (AUT-035, AUT-036, GRILL-001).

    The AI decision is snapshotted as inert text; it is never recomputed here.
    ``EDIT_CONTENT`` requires a non-empty edited payload, while ``APPROVE`` and
    ``REJECT`` reject one so an edit is never smuggled in with another action.
    """

    if str(schema_version) != HUMAN_REVIEW_SCHEMA_VERSION:
        raise human_review_input_invalid_error(
            "schema_version de HumanReview não suportada",
            context={"field": "schema_version", "supported": HUMAN_REVIEW_SCHEMA_VERSION},
        )
    resolved_candidate = _require_clean_text(candidate_id, field_name="candidate_id", max_length=64)
    decision = _coerce_human_decision(human_decision)
    resolved_reason = _require_clean_text(
        reason, field_name="reason", max_length=MAX_REVIEW_TEXT_LENGTH
    )
    resolved_note = (
        None
        if note is None
        else _require_clean_text(note, field_name="note", max_length=MAX_REVIEW_TEXT_LENGTH)
    )
    resolved_ai_review_id = (
        None
        if ai_review_id is None
        else _require_clean_text(ai_review_id, field_name="ai_review_id", max_length=64)
    )
    resolved_ai_decision = (
        None
        if ai_decision is None
        else _require_clean_text(ai_decision, field_name="ai_decision", max_length=32)
    )
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise human_review_input_invalid_error(
            "correlation_id é obrigatório", context={"field": "correlation_id"}
        )

    resolved_edit: EditedContent | None = None
    if decision is HumanDecision.EDIT_CONTENT:
        if edited_content is None:
            raise human_review_input_invalid_error(
                "EDIT_CONTENT exige edited_content",
                context={"field": "edited_content"},
            )
        resolved_edit = build_edited_content(edited_content)
    elif edited_content is not None:
        raise human_review_input_invalid_error(
            "edited_content só é aceito em EDIT_CONTENT",
            context={"field": "edited_content", "human_decision": decision.value},
        )

    reference = _to_utc(now)
    return HumanReview(
        human_review_id=(
            str(id_factory("hr"))
            if human_review_id is None
            else _require_clean_text(human_review_id, field_name="human_review_id", max_length=64)
        ),
        candidate_id=resolved_candidate,
        ai_review_id=resolved_ai_review_id,
        ai_decision=resolved_ai_decision,
        human_decision=decision,
        reason=resolved_reason,
        note=resolved_note,
        edited_content=resolved_edit,
        correlation_id=correlation_id.strip(),
        audit_event_id=str(id_factory("aud")),
        reviewed_at=reference,
    )


__all__ = [
    "AUDIT_SOURCE_HUMAN_REVIEW",
    "ENTITY_HUMAN_REVIEW",
    "HUMAN_REVIEW_INPUT_INVALID",
    "HUMAN_REVIEW_NOT_FOUND",
    "HUMAN_REVIEW_SCHEMA_VERSION",
    "MAX_REVIEW_TEXT_LENGTH",
    "REVIEW_CANDIDATE_NOT_FOUND",
    "EditedContent",
    "HumanDecision",
    "HumanReview",
    "HumanReviewError",
    "build_edited_content",
    "build_human_review",
    "human_review_input_invalid_error",
    "human_review_not_found_error",
    "review_candidate_not_found_error",
]
