"""TrackingContext: internal tracking kept separate from the external label
(RDR-070, RECON-003).

``docs/09_PUBLISHING.md`` and ``docs/04_DATA_CONTRACTS.md`` separate the
**internal** tracking reference from the **external** marketplace label: the
internal reference is what the Core owns and correlates, while ``tracking_label``
is the alphanumeric value a human configured in the marketplace. This module
implements that split without ever coupling the domain to FastAPI/SQLAlchemy/
Chrome (AUT-397):

* the external label is validated against ``[a-z0-9]{1,30}`` and is **never**
  silently normalized (uppercase, separators or truncation fail closed);
* the label is resolved through an explicit, versioned and hashed mapping
  (``config/tracking-labels.json``) whose uniqueness and association are
  validated, so the system never assumes a label already exists in the account;
* the approved baseline mapping is intentionally **empty**: ``rbtgoffer`` is a
  syntactic example, not an authorized label, so an unmapped slice is an explicit
  gap (``TRACKING_MAPPING_NOT_CONFIGURED``) instead of an invented label.

Tracking carries no PII (AUT-169): only the internal reference, the configured
label and the mapping version/hash are exposed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from radar.domain.capture import (
    IdFactory,
    Marketplace,
    default_id_factory,
    find_sensitive_fields,
    sanitize_single_line,
)
from radar.domain.errors import RadarError, RadarException
from radar.domain.taxonomy import Brand

#: Version of the public TrackingContext contract.
TRACKING_SCHEMA_VERSION = "1.0"

#: Version of the tracking-label mapping document schema.
TRACKING_LABELS_SCHEMA_VERSION = "1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
TRACKING_LABEL_INVALID = "RAD-LINK-004"
TRACKING_MAPPING_NOT_CONFIGURED = "RAD-LINK-005"
TRACKING_LABELS_INVALID = "RAD-CFG-015"

#: Warning emitted when a slice has no approved external label.
WARNING_TRACKING_MAPPING_NOT_CONFIGURED = "TRACKING_MAPPING_NOT_CONFIGURED"

#: The only accepted external label shape (RECON-003). Never normalized.
TRACKING_LABEL_PATTERN = re.compile(r"^[a-z0-9]{1,30}$")
MAX_TRACKING_LABEL_LENGTH = 30
MAX_INTERNAL_REFERENCE_LENGTH = 128

#: Baseline mapping version when no file is configured (empty, no label assumed).
BASELINE_TRACKING_MAPPING_VERSION = "tracking-labels-1.0"


class TrackingError(RadarException):
    """Raised when tracking cannot be resolved safely."""


def tracking_label_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> TrackingError:
    """Build the structured error for an invalid/unassociated external label."""

    return TrackingError(
        RadarError(
            code=TRACKING_LABEL_INVALID,
            message=message,
            retryable=False,
            action=(
                "Configurar uma etiqueta válida [a-z0-9]{1,30} no mapeamento "
                "versionado; nunca normalizar o valor"
            ),
            context=dict(context or {}),
        )
    )


def tracking_mapping_not_configured_error(
    *, internal_reference: str, marketplace: Marketplace
) -> TrackingError:
    """Build the structured gap error when no approved label maps the slice."""

    return TrackingError(
        RadarError(
            code=TRACKING_MAPPING_NOT_CONFIGURED,
            message="Nenhuma etiqueta aprovada mapeia a referência interna",
            retryable=False,
            action=(
                "Configurar explicitamente o mapeamento de etiquetas "
                "(config/tracking-labels.json) para brand/marketplace"
            ),
            context={
                "internal_reference": internal_reference,
                "marketplace": marketplace.value,
            },
        )
    )


def tracking_labels_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> TrackingError:
    """Build the structured, fail-closed error for an invalid mapping config."""

    return TrackingError(
        RadarError(
            code=TRACKING_LABELS_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o mapeamento de etiquetas versionado e carregar novamente",
            context=dict(context or {}),
        )
    )


def _label_rejection_reason(value: str) -> str | None:
    """Explain why a label is invalid without ever rewriting it."""

    if not value:
        return "EMPTY"
    if len(value) > MAX_TRACKING_LABEL_LENGTH:
        return "TOO_LONG"
    if any(character.isupper() for character in value):
        return "UPPERCASE_NOT_ALLOWED"
    if any(not character.isalnum() for character in value):
        return "SEPARATOR_OR_SYMBOL_NOT_ALLOWED"
    return None


def validate_tracking_label(value: object, *, field_name: str = "tracking_label") -> str:
    """Validate an external tracking label against ``[a-z0-9]{1,30}``.

    The value is returned unchanged when valid; an uppercase, separated, empty or
    oversized label fails closed with ``RAD-LINK-004`` and is **never** lowercased,
    stripped of separators or truncated to fit (RECON-003).
    """

    if not isinstance(value, str):
        raise tracking_label_invalid_error(
            "tracking_label deve ser texto",
            context={"field": field_name, "pattern": TRACKING_LABEL_PATTERN.pattern},
        )
    if TRACKING_LABEL_PATTERN.fullmatch(value) is not None:
        return value
    reason = _label_rejection_reason(value)
    raise tracking_label_invalid_error(
        "tracking_label inválida",
        context={
            "field": field_name,
            "pattern": TRACKING_LABEL_PATTERN.pattern,
            "max_length": MAX_TRACKING_LABEL_LENGTH,
            "reason": reason or "INVALID_CHARSET",
            "length": len(value),
        },
    )


@dataclass(frozen=True, slots=True)
class TrackingLabelEntry:
    """One explicit, auditable association: internal reference -> external label."""

    internal_reference: str
    marketplace: Marketplace
    label: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "internal_reference": self.internal_reference,
            "marketplace": self.marketplace.value,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class TrackingLabelMapping:
    """Versioned, hashed mapping of internal references to external labels.

    The mapping is data, not a hardcoded conditional (AUT-045): the operator
    configures the label explicitly and the system records the version/hash it
    resolved from. The approved baseline is empty, so no label is assumed.
    """

    mapping_version: str
    content_hash: str
    entries: Mapping[str, TrackingLabelEntry]
    schema_version: str = TRACKING_LABELS_SCHEMA_VERSION

    def resolve(
        self, internal_reference: str, marketplace: Marketplace
    ) -> TrackingLabelEntry | None:
        """Return the mapped entry for the slice, or ``None`` when unconfigured."""

        entry = self.entries.get(internal_reference)
        if entry is None or entry.marketplace is not marketplace:
            return None
        return entry

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mapping_version": self.mapping_version,
            "content_hash": self.content_hash,
            "entry_count": len(self.entries),
            "entries": [entry.to_contract() for entry in self.entries.values()],
        }


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_version(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise tracking_labels_invalid_error(
            f"{field_name} do mapeamento de etiquetas deve ser texto",
            context={"field": field_name},
        )
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 64:
        raise tracking_labels_invalid_error(
            f"{field_name} do mapeamento de etiquetas inválido",
            context={"field": field_name, "max_length": 64},
        )
    return cleaned


def _require_internal_reference(value: object) -> str:
    if not isinstance(value, str):
        raise tracking_labels_invalid_error(
            "internal_reference do mapeamento deve ser texto",
            context={"field": "internal_reference"},
        )
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_INTERNAL_REFERENCE_LENGTH:
        raise tracking_labels_invalid_error(
            "internal_reference do mapeamento inválida",
            context={"field": "internal_reference", "max_length": MAX_INTERNAL_REFERENCE_LENGTH},
        )
    return cleaned


def build_tracking_label_mapping(data: Mapping[str, Any]) -> TrackingLabelMapping:
    """Validate, enforce uniqueness and hash an explicit label mapping.

    Unknown fields and sensitive field names are refused before anything is
    hashed. Each label is validated with :func:`validate_tracking_label`; a
    duplicated ``internal_reference`` or a duplicated ``(marketplace, label)``
    fails closed, so the mapping stays an unambiguous, auditable association.
    """

    if not isinstance(data, Mapping):
        raise tracking_labels_invalid_error("mapeamento de etiquetas deve ser um objeto JSON")
    sensitive = find_sensitive_fields(data)
    if sensitive:
        raise tracking_labels_invalid_error(
            "mapeamento de etiquetas contém campos sensíveis não permitidos",
            context={"fields": list(sensitive)},
        )
    allowed = {"schema_version", "mapping_version", "entries"}
    unknown = sorted({str(key) for key in data} - allowed)
    if unknown:
        raise tracking_labels_invalid_error(
            "mapeamento de etiquetas contém campos desconhecidos",
            context={"fields": unknown},
        )
    schema_version = str(data.get("schema_version", TRACKING_LABELS_SCHEMA_VERSION))
    if schema_version != TRACKING_LABELS_SCHEMA_VERSION:
        raise tracking_labels_invalid_error(
            "schema_version do mapeamento de etiquetas não suportada",
            context={"supported": TRACKING_LABELS_SCHEMA_VERSION},
        )
    mapping_version = _require_version(
        data.get("mapping_version", BASELINE_TRACKING_MAPPING_VERSION),
        field_name="mapping_version",
    )
    raw_entries = data.get("entries", [])
    if isinstance(raw_entries, (str, bytes)) or not isinstance(raw_entries, Sequence):
        raise tracking_labels_invalid_error("entries do mapeamento deve ser uma lista")

    entries: dict[str, TrackingLabelEntry] = {}
    seen_labels: dict[tuple[Marketplace, str], str] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            raise tracking_labels_invalid_error("cada entry do mapeamento deve ser um objeto")
        entry_allowed = {"internal_reference", "marketplace", "label"}
        entry_unknown = sorted({str(key) for key in raw_entry} - entry_allowed)
        if entry_unknown:
            raise tracking_labels_invalid_error(
                "entry do mapeamento contém campos desconhecidos",
                context={"fields": entry_unknown},
            )
        internal_reference = _require_internal_reference(raw_entry.get("internal_reference"))
        try:
            marketplace = Marketplace(str(raw_entry.get("marketplace")))
        except ValueError as exc:
            raise tracking_labels_invalid_error(
                "marketplace inválido no mapeamento de etiquetas",
                context={"allowed": [item.value for item in Marketplace]},
            ) from exc
        label = validate_tracking_label(raw_entry.get("label"))
        if internal_reference in entries:
            raise tracking_labels_invalid_error(
                "internal_reference duplicada no mapeamento de etiquetas",
                context={"internal_reference": internal_reference},
            )
        label_key = (marketplace, label)
        if label_key in seen_labels:
            raise tracking_labels_invalid_error(
                "etiqueta duplicada no mapeamento de etiquetas",
                context={
                    "marketplace": marketplace.value,
                    "label": label,
                    "internal_reference": internal_reference,
                },
            )
        seen_labels[label_key] = internal_reference
        entries[internal_reference] = TrackingLabelEntry(
            internal_reference=internal_reference,
            marketplace=marketplace,
            label=label,
        )

    content_hash = _canonical_hash(
        {
            "schema_version": TRACKING_LABELS_SCHEMA_VERSION,
            "mapping_version": mapping_version,
            "entries": [
                entry.to_contract()
                for _key, entry in sorted(entries.items(), key=lambda item: item[0])
            ],
        }
    )
    return TrackingLabelMapping(
        mapping_version=mapping_version,
        content_hash=content_hash,
        entries=entries,
    )


def _build_baseline() -> TrackingLabelMapping:
    return build_tracking_label_mapping(
        {
            "schema_version": TRACKING_LABELS_SCHEMA_VERSION,
            "mapping_version": BASELINE_TRACKING_MAPPING_VERSION,
            "entries": [],
        }
    )


#: Approved baseline: versioned/hashed structure with no label assumed.
APPROVED_TRACKING_LABEL_MAPPING: TrackingLabelMapping = _build_baseline()


@dataclass(frozen=True, slots=True)
class TrackingContext:
    """Internal tracking of one Opportunity, separate from the external label.

    ``external_label`` is the resolved marketplace label (``None`` when the slice
    is unmapped); ``tracking_context_id`` and ``internal_reference`` are the
    internal reference the Core correlates. No PII is carried (AUT-169).
    """

    tracking_context_id: str
    opportunity_id: str
    marketplace: Marketplace
    brand: Brand
    internal_reference: str
    mapping_version: str
    mapping_hash: str
    external_label: str | None = None
    configured: bool = False
    schema_version: str = TRACKING_SCHEMA_VERSION

    @property
    def warning_code(self) -> str | None:
        return None if self.configured else WARNING_TRACKING_MAPPING_NOT_CONFIGURED

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tracking_context_id": self.tracking_context_id,
            "opportunity_id": self.opportunity_id,
            "marketplace": self.marketplace.value,
            "brand": self.brand.value,
            "internal_reference": self.internal_reference,
            "external_label": self.external_label,
            "mapping_version": self.mapping_version,
            "mapping_hash": self.mapping_hash,
            "configured": self.configured,
        }


def build_tracking_context(
    *,
    opportunity_id: str,
    marketplace: Marketplace,
    brand: Brand,
    internal_reference: str,
    mapping: TrackingLabelMapping,
    tracking_context_id: object | None = None,
    id_factory: IdFactory = default_id_factory,
) -> TrackingContext:
    """Resolve the internal context and its external label from the mapping.

    A missing association is an explicit gap: the context is returned with
    ``configured=False`` and ``external_label=None`` so the caller blocks the link
    with ``TRACKING_MAPPING_NOT_CONFIGURED`` instead of assuming a label exists.
    """

    reference = _require_internal_reference(internal_reference)
    entry = mapping.resolve(reference, marketplace)
    resolved_id = (
        str(id_factory("trk"))
        if tracking_context_id is None
        else sanitize_single_line(str(tracking_context_id))
    )
    return TrackingContext(
        tracking_context_id=resolved_id,
        opportunity_id=sanitize_single_line(str(opportunity_id)),
        marketplace=marketplace,
        brand=brand,
        internal_reference=reference,
        mapping_version=mapping.mapping_version,
        mapping_hash=mapping.content_hash,
        external_label=None if entry is None else entry.label,
        configured=entry is not None,
    )


__all__ = [
    "APPROVED_TRACKING_LABEL_MAPPING",
    "BASELINE_TRACKING_MAPPING_VERSION",
    "MAX_INTERNAL_REFERENCE_LENGTH",
    "MAX_TRACKING_LABEL_LENGTH",
    "TRACKING_LABELS_INVALID",
    "TRACKING_LABELS_SCHEMA_VERSION",
    "TRACKING_LABEL_INVALID",
    "TRACKING_LABEL_PATTERN",
    "TRACKING_MAPPING_NOT_CONFIGURED",
    "TRACKING_SCHEMA_VERSION",
    "WARNING_TRACKING_MAPPING_NOT_CONFIGURED",
    "TrackingContext",
    "TrackingError",
    "TrackingLabelEntry",
    "TrackingLabelMapping",
    "build_tracking_context",
    "build_tracking_label_mapping",
    "tracking_label_invalid_error",
    "tracking_labels_invalid_error",
    "tracking_mapping_not_configured_error",
    "validate_tracking_label",
]
