"""Publication Inbox/detail read models (TKT-27, RDR-061, RDR-062).

This module implements the consultation half of TKT-27: the Publicações screen of
the Control Center reads the real persisted Publication rows and the *preview* of
an Opportunity that is ready to publish, all through the public boundary. It is
framework-free (no FastAPI/SQLAlchemy/Chrome): the infrastructure repository
composes the persisted rows into these immutable views, and nothing is recomputed
or invented here (``docs/11_OPERATIONS_AND_UI.md``).

Two entry kinds are exposed:

* ``PUBLICATION`` -- a persisted :class:`~radar.domain.publication.Publication`
  (its ``status`` is the lifecycle state, including the suspended ``UNKNOWN``);
* ``PREVIEW`` -- a read-model projection of an Opportunity in
  ``READY_TO_PUBLISH`` with a validated preview and an affiliate link but no open
  publication yet. It is **not** a persisted Publication entity (AUT-034): it is
  the "preview" the operator approves, and boarding approval always goes through
  the audited ``POST /opportunities/{id}/publications`` contract.

Reading never sends: ``preview``/``detail``/``inbox`` are pure queries. The
unknown-result suspension is surfaced with its open HumanAction so the operator is
routed to the intervention instead of an automatic resend (GRILL-002, ADR 0001).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from radar.domain.publication import (
    Publication,
    publication_not_found_error,
)

#: Version of the public publication read contracts (``docs/04_DATA_CONTRACTS.md``).
PUBLICATION_READ_SCHEMA_VERSION = "1.0"

#: Entry kinds of the Publication Inbox (RDR-061).
KIND_PUBLICATION = "PUBLICATION"
KIND_PREVIEW = "PREVIEW"

#: Provenance labels of the ``last_validation`` view.
VALIDATION_SOURCE_CREATION = "CREATION"
VALIDATION_SOURCE_REVALIDATION = "REVALIDATION"


@dataclass(frozen=True, slots=True)
class PublicationProductView:
    """Product/offer facts shown in the Inbox and detail (RDR-061/062)."""

    marketplace: str | None
    external_id: str | None
    title: str | None
    url: str | None
    brand: str | None
    current_price: str | None

    def to_contract(self) -> dict[str, Any]:
        return {
            "marketplace": self.marketplace,
            "external_id": self.external_id,
            "title": self.title,
            "url": self.url,
            "brand": self.brand,
            "current_price": self.current_price,
        }


@dataclass(frozen=True, slots=True)
class PublicationLinkView:
    """The literal affiliate link and its tracking context (AUT-166..AUT-171)."""

    affiliate_link_id: str
    affiliate_url: str
    productive: bool
    generation_method: str
    status: str
    tracking_context_id: str
    tracking_internal_reference: str
    tracking_label: str
    tracking_mapping_version: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "affiliate_link_id": self.affiliate_link_id,
            "affiliate_url": self.affiliate_url,
            "productive": self.productive,
            "generation_method": self.generation_method,
            "status": self.status,
            "tracking_context_id": self.tracking_context_id,
            "tracking_internal_reference": self.tracking_internal_reference,
            "tracking_label": self.tracking_label,
            "tracking_mapping_version": self.tracking_mapping_version,
        }


@dataclass(frozen=True, slots=True)
class ContentPreviewView:
    """The deterministically rendered preview of the ContentGeneration (RDR-069).

    ``text`` is the effective content prepared for the send (backend price, literal
    affiliate URL, disclosure and tracking already applied); the AI copy stays
    separate in the ``generated`` fields (AUT-034, AUT-163).
    """

    content_generation_id: str
    channel: str
    status: str
    stale: bool
    renderer_version: str
    headline: str
    body: str
    cta: str
    text: str
    price: str | None
    affiliate_url: str
    disclosure: str
    tracking: Mapping[str, Any]

    def to_contract(self) -> dict[str, Any]:
        return {
            "content_generation_id": self.content_generation_id,
            "channel": self.channel,
            "status": self.status,
            "stale": self.stale,
            "renderer_version": self.renderer_version,
            "headline": self.headline,
            "body": self.body,
            "cta": self.cta,
            "text": self.text,
            "price": self.price,
            "affiliate_url": self.affiliate_url,
            "disclosure": self.disclosure,
            "tracking": dict(self.tracking),
        }


@dataclass(frozen=True, slots=True)
class PublicationValidationView:
    """The last validation observed for an entry (RDR-062, "última validação")."""

    validated_at: str
    allowed: bool | None
    reason_code: str | None
    source: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "validated_at": self.validated_at,
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class PublicationTimelineEntry:
    """One append-only timeline entry (PublicationEvent or AuditEvent)."""

    event_type: str
    source: str
    occurred_at: str
    correlation_id: str
    payload: Mapping[str, Any]

    def to_contract(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "source": self.source,
            "occurred_at": self.occurred_at,
            "correlation_id": self.correlation_id,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class PublicationInboxItem:
    """One row of the Publication Inbox (RDR-061)."""

    entry_id: str
    kind: str
    publication_id: str | None
    opportunity_id: str
    content_generation_id: str | None
    brand: str | None
    channel: str | None
    destination_id: str | None
    status: str
    revision: int | None
    external_message_id: str | None
    published_price: str | None
    product: PublicationProductView
    last_validation: PublicationValidationView | None
    updated_at: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "kind": self.kind,
            "publication_id": self.publication_id,
            "opportunity_id": self.opportunity_id,
            "content_generation_id": self.content_generation_id,
            "brand": self.brand,
            "channel": self.channel,
            "destination_id": self.destination_id,
            "status": self.status,
            "revision": self.revision,
            "external_message_id": self.external_message_id,
            "published_price": self.published_price,
            "product": self.product.to_contract(),
            "last_validation": (
                None if self.last_validation is None else self.last_validation.to_contract()
            ),
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class PublicationDetail:
    """Publication detail read model of the Publicações screen (RDR-062)."""

    kind: str
    opportunity_id: str
    publication: Publication | None
    product: PublicationProductView
    preview: ContentPreviewView | None
    link: PublicationLinkView | None
    revision: int | None
    external_message_id: str | None
    last_validation: PublicationValidationView | None
    timeline: tuple[PublicationTimelineEntry, ...]
    human_actions: tuple[Mapping[str, Any], ...]

    def to_contract(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "opportunity_id": self.opportunity_id,
            "publication": (None if self.publication is None else self.publication.to_contract()),
            "product": self.product.to_contract(),
            "preview": None if self.preview is None else self.preview.to_contract(),
            "link": None if self.link is None else self.link.to_contract(),
            "revision": self.revision,
            "external_message_id": self.external_message_id,
            "last_validation": (
                None if self.last_validation is None else self.last_validation.to_contract()
            ),
            "timeline": [entry.to_contract() for entry in self.timeline],
            "human_actions": [dict(action) for action in self.human_actions],
        }


class PublicationReadStore(Protocol):
    """Read port that composes the persisted rows into the publication views."""

    def list_publications(self) -> tuple[PublicationInboxItem, ...]: ...

    def list_pending_previews(self) -> tuple[PublicationInboxItem, ...]: ...

    def get_publication_detail(self, publication_id: str) -> PublicationDetail | None: ...

    def get_preview_detail(self, opportunity_id: str) -> PublicationDetail | None: ...


@dataclass(slots=True)
class PublicationReadService:
    """Serve the Publication Inbox/detail without ever sending anything."""

    store: PublicationReadStore

    def inbox(self) -> tuple[PublicationInboxItem, ...]:
        """Return the Inbox entries, newest first (RDR-061).

        Persisted Publications and ready previews are merged so the operator sees
        both the send history and the offers waiting for an explicit approval.
        """

        items = (*self.store.list_pending_previews(), *self.store.list_publications())
        return tuple(sorted(items, key=lambda item: (item.updated_at, item.entry_id), reverse=True))

    def detail(self, publication_id: str) -> PublicationDetail:
        """Return a persisted Publication detail or fail closed with ``RAD-PUB-002``."""

        detail = self.store.get_publication_detail(publication_id)
        if detail is None:
            raise publication_not_found_error(publication_id)
        return detail

    def preview(self, opportunity_id: str) -> PublicationDetail:
        """Return the ready preview of an Opportunity or fail closed ``RAD-PUB-002``.

        A preview that is no longer available (already published/expired or without
        validated content) is reported as not found, so the UI never fabricates a
        publication capability the Core does not have.
        """

        detail = self.store.get_preview_detail(opportunity_id)
        if detail is None:
            raise publication_not_found_error(opportunity_id)
        return detail


__all__ = [
    "KIND_PREVIEW",
    "KIND_PUBLICATION",
    "PUBLICATION_READ_SCHEMA_VERSION",
    "VALIDATION_SOURCE_CREATION",
    "VALIDATION_SOURCE_REVALIDATION",
    "ContentPreviewView",
    "PublicationDetail",
    "PublicationInboxItem",
    "PublicationLinkView",
    "PublicationProductView",
    "PublicationReadService",
    "PublicationReadStore",
    "PublicationTimelineEntry",
    "PublicationValidationView",
]
