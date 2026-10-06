"""Versioned Knowledge Pack of the editorial AI (RDR-045, AUT-205..AUT-207).

The Knowledge Pack is the editorial/runtime context the AI may use, kept separate
from operational configuration (AUT-205) and from the AI provider itself. Runtime
carries only the context needed for a task
(``brand + channel + task``, ``docs/06_AI_ENGINE.md``): this module resolves a
compact :class:`KnowledgeContext` for a brand/channel and versions/hashes the
whole pack so every AI review records the exact knowledge and prompt version it
was produced from (AUT-207, ``docs/03_DOMAIN_MODEL.md``).

The pack never carries secrets: values live in the pack, credentials live behind
the :class:`~radar.domain.secrets.SecretsProvider` (AUT-210). The approved
baseline is intentionally **empty**: the SDD fixes the structure and the system
contract, but not brand/channel prose, so a missing entry is an explicit gap
(``KNOWLEDGE_CONTEXT_NOT_CONFIGURED``) instead of invented guidance. The module
is framework-free (no FastAPI/SQLAlchemy/Chrome, AUT-397).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from radar.domain.capture import find_sensitive_fields
from radar.domain.errors import RadarError, RadarException
from radar.domain.taxonomy import Brand

#: Version of the Knowledge Pack document schema.
KNOWLEDGE_SCHEMA_VERSION = "1.0"

#: Version of the public Knowledge context contract.
KNOWLEDGE_CONTEXT_SCHEMA_VERSION = "1.0"

#: Baseline version/prompt identifiers when no pack file is configured.
BASELINE_KNOWLEDGE_VERSION = "knowledge-pack-1.0"
BASELINE_PROMPT_VERSION = "editorial-review-1.0"

#: Error code (see ``docs/ERROR_CATALOG.md``).
KNOWLEDGE_INVALID = "RAD-CFG-014"

#: Warning emitted when a brand/channel has no approved guidance in the pack.
WARNING_KNOWLEDGE_CONTEXT_NOT_CONFIGURED = "KNOWLEDGE_CONTEXT_NOT_CONFIGURED"

#: Max length of a guidance line, so a config can never smuggle a payload.
MAX_GUIDANCE_LENGTH = 512
MAX_GUIDANCE_ITEMS = 32


class Channel(StrEnum):
    """Publishing channels supported by V1 (``docs/04_DATA_CONTRACTS.md``)."""

    TELEGRAM = "TELEGRAM"
    WHATSAPP = "WHATSAPP"


class KnowledgeInvalidError(RadarException):
    """Raised when a Knowledge Pack fails schema/semantic validation."""


def knowledge_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> KnowledgeInvalidError:
    """Build the structured, fail-closed error for an invalid Knowledge Pack."""

    return KnowledgeInvalidError(
        RadarError(
            code=KNOWLEDGE_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o Knowledge Pack versionado e carregar novamente",
            context=dict(context or {}),
        )
    )


def _clean_lines(
    value: object, *, field_name: str, brand: Brand, channel: Channel
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise knowledge_invalid_error(
            "guidance do Knowledge Pack deve ser uma lista de textos",
            context={"field": field_name, "brand": brand.value, "channel": channel.value},
        )
    lines: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise knowledge_invalid_error(
                "guidance do Knowledge Pack deve conter textos",
                context={"field": field_name, "brand": brand.value, "channel": channel.value},
            )
        cleaned = item.strip()
        if not cleaned:
            raise knowledge_invalid_error(
                "guidance do Knowledge Pack não pode ser vazia",
                context={"field": field_name, "brand": brand.value, "channel": channel.value},
            )
        if len(cleaned) > MAX_GUIDANCE_LENGTH:
            raise knowledge_invalid_error(
                "guidance do Knowledge Pack excede o tamanho máximo",
                context={"field": field_name, "max_length": MAX_GUIDANCE_LENGTH},
            )
        lines.append(cleaned)
    if len(lines) > MAX_GUIDANCE_ITEMS:
        raise knowledge_invalid_error(
            "guidance do Knowledge Pack excede o número máximo de itens",
            context={"field": field_name, "max_items": MAX_GUIDANCE_ITEMS},
        )
    return tuple(lines)


@dataclass(frozen=True, slots=True)
class KnowledgeEntry:
    """Approved editorial context for one ``brand x channel`` slice."""

    brand: Brand
    channel: Channel
    system_contract: tuple[str, ...] = ()
    brand_guidance: tuple[str, ...] = ()
    channel_guidance: tuple[str, ...] = ()

    @property
    def is_configured(self) -> bool:
        return bool(self.system_contract or self.brand_guidance or self.channel_guidance)

    def to_contract(self) -> dict[str, Any]:
        return {
            "brand": self.brand.value,
            "channel": self.channel.value,
            "system_contract": list(self.system_contract),
            "brand_guidance": list(self.brand_guidance),
            "channel_guidance": list(self.channel_guidance),
        }


@dataclass(frozen=True, slots=True)
class KnowledgePack:
    """Versioned, hashed pack of editorial context (AUT-206, AUT-207)."""

    knowledge_version: str
    prompt_version: str
    content_hash: str
    entries: Mapping[tuple[Brand, Channel], KnowledgeEntry]
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def entry(self, brand: Brand, channel: Channel) -> KnowledgeEntry | None:
        return self.entries.get((brand, channel))

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "knowledge_version": self.knowledge_version,
            "prompt_version": self.prompt_version,
            "content_hash": self.content_hash,
            "entry_count": len(self.entries),
            "entries": [entry.to_contract() for entry in self.entries.values()],
        }


@dataclass(frozen=True, slots=True)
class KnowledgeContext:
    """Minimal context selected for one ``brand + channel + task`` (RDR-045)."""

    knowledge_version: str
    knowledge_hash: str
    prompt_version: str
    brand: Brand
    channel: Channel
    task: str
    system_contract: tuple[str, ...] = ()
    brand_guidance: tuple[str, ...] = ()
    channel_guidance: tuple[str, ...] = ()
    configured: bool = False

    @property
    def warning_code(self) -> str | None:
        return None if self.configured else WARNING_KNOWLEDGE_CONTEXT_NOT_CONFIGURED

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": KNOWLEDGE_CONTEXT_SCHEMA_VERSION,
            "knowledge_version": self.knowledge_version,
            "knowledge_hash": self.knowledge_hash,
            "prompt_version": self.prompt_version,
            "brand": self.brand.value,
            "channel": self.channel.value,
            "task": self.task,
            "configured": self.configured,
            "system_contract": list(self.system_contract),
            "brand_guidance": list(self.brand_guidance),
            "channel_guidance": list(self.channel_guidance),
        }


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_version(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise knowledge_invalid_error(
            f"{field_name} do Knowledge Pack deve ser texto", context={"field": field_name}
        )
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 64:
        raise knowledge_invalid_error(
            f"{field_name} do Knowledge Pack inválido",
            context={"field": field_name, "max_length": 64},
        )
    return cleaned


def build_knowledge_pack(data: Mapping[str, Any]) -> KnowledgePack:
    """Validate and hash a Knowledge Pack, failing closed on any gap.

    Unknown fields are rejected (``extra=forbid`` semantics) and sensitive field
    names are refused before anything is hashed, so a pack can never carry a
    credential into the AI context (AUT-210, AUT-299).
    """

    if not isinstance(data, Mapping):
        raise knowledge_invalid_error("Knowledge Pack deve ser um objeto JSON")
    sensitive = find_sensitive_fields(data)
    if sensitive:
        raise knowledge_invalid_error(
            "Knowledge Pack contém campos sensíveis não permitidos",
            context={"fields": list(sensitive)},
        )
    allowed = {"schema_version", "knowledge_version", "prompt_version", "entries"}
    unknown = sorted({str(key) for key in data} - allowed)
    if unknown:
        raise knowledge_invalid_error(
            "Knowledge Pack contém campos desconhecidos", context={"fields": unknown}
        )
    schema_version = str(data.get("schema_version", KNOWLEDGE_SCHEMA_VERSION))
    if schema_version != KNOWLEDGE_SCHEMA_VERSION:
        raise knowledge_invalid_error(
            "schema_version do Knowledge Pack não suportada",
            context={"supported": KNOWLEDGE_SCHEMA_VERSION},
        )
    knowledge_version = _require_version(
        data.get("knowledge_version", BASELINE_KNOWLEDGE_VERSION), field_name="knowledge_version"
    )
    prompt_version = _require_version(
        data.get("prompt_version", BASELINE_PROMPT_VERSION), field_name="prompt_version"
    )
    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes)):
        raise knowledge_invalid_error("entries do Knowledge Pack deve ser uma lista")

    entries: dict[tuple[Brand, Channel], KnowledgeEntry] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            raise knowledge_invalid_error("cada entry do Knowledge Pack deve ser um objeto")
        entry_allowed = {
            "brand",
            "channel",
            "system_contract",
            "brand_guidance",
            "channel_guidance",
        }
        entry_unknown = sorted({str(key) for key in raw_entry} - entry_allowed)
        if entry_unknown:
            raise knowledge_invalid_error(
                "entry do Knowledge Pack contém campos desconhecidos",
                context={"fields": entry_unknown},
            )
        try:
            brand = Brand(str(raw_entry.get("brand")))
        except ValueError as exc:
            raise knowledge_invalid_error(
                "brand inválida no Knowledge Pack",
                context={"allowed": [item.value for item in Brand]},
            ) from exc
        try:
            channel = Channel(str(raw_entry.get("channel")))
        except ValueError as exc:
            raise knowledge_invalid_error(
                "channel inválido no Knowledge Pack",
                context={"allowed": [item.value for item in Channel]},
            ) from exc
        key = (brand, channel)
        if key in entries:
            raise knowledge_invalid_error(
                "entry duplicado no Knowledge Pack",
                context={"brand": brand.value, "channel": channel.value},
            )
        entries[key] = KnowledgeEntry(
            brand=brand,
            channel=channel,
            system_contract=_clean_lines(
                raw_entry.get("system_contract"),
                field_name="system_contract",
                brand=brand,
                channel=channel,
            ),
            brand_guidance=_clean_lines(
                raw_entry.get("brand_guidance"),
                field_name="brand_guidance",
                brand=brand,
                channel=channel,
            ),
            channel_guidance=_clean_lines(
                raw_entry.get("channel_guidance"),
                field_name="channel_guidance",
                brand=brand,
                channel=channel,
            ),
        )

    content_hash = _canonical_hash(
        {
            "schema_version": KNOWLEDGE_SCHEMA_VERSION,
            "knowledge_version": knowledge_version,
            "prompt_version": prompt_version,
            "entries": [
                entry.to_contract()
                for _key, entry in sorted(entries.items(), key=lambda item: item[0])
            ],
        }
    )
    return KnowledgePack(
        knowledge_version=knowledge_version,
        prompt_version=prompt_version,
        content_hash=content_hash,
        entries=entries,
    )


def _build_baseline() -> KnowledgePack:
    return build_knowledge_pack(
        {
            "schema_version": KNOWLEDGE_SCHEMA_VERSION,
            "knowledge_version": BASELINE_KNOWLEDGE_VERSION,
            "prompt_version": BASELINE_PROMPT_VERSION,
            "entries": [],
        }
    )


#: Approved baseline: versioned/hashed structure with no invented editorial content.
APPROVED_KNOWLEDGE_PACK: KnowledgePack = _build_baseline()


def select_knowledge_context(
    pack: KnowledgePack, *, brand: Brand, channel: Channel, task: str
) -> KnowledgeContext:
    """Resolve the minimal context of one ``brand + channel + task`` slice.

    An absent slice is an explicit gap: the context keeps the version/hash so the
    AIReview is traceable, marks ``configured=false`` and lets the caller emit
    ``KNOWLEDGE_CONTEXT_NOT_CONFIGURED`` instead of inventing guidance.
    """

    entry = pack.entry(brand, channel)
    if entry is None:
        return KnowledgeContext(
            knowledge_version=pack.knowledge_version,
            knowledge_hash=pack.content_hash,
            prompt_version=pack.prompt_version,
            brand=brand,
            channel=channel,
            task=task,
        )
    return KnowledgeContext(
        knowledge_version=pack.knowledge_version,
        knowledge_hash=pack.content_hash,
        prompt_version=pack.prompt_version,
        brand=brand,
        channel=channel,
        task=task,
        system_contract=entry.system_contract,
        brand_guidance=entry.brand_guidance,
        channel_guidance=entry.channel_guidance,
        configured=entry.is_configured,
    )


__all__ = [
    "APPROVED_KNOWLEDGE_PACK",
    "BASELINE_KNOWLEDGE_VERSION",
    "BASELINE_PROMPT_VERSION",
    "KNOWLEDGE_CONTEXT_SCHEMA_VERSION",
    "KNOWLEDGE_INVALID",
    "KNOWLEDGE_SCHEMA_VERSION",
    "MAX_GUIDANCE_ITEMS",
    "MAX_GUIDANCE_LENGTH",
    "WARNING_KNOWLEDGE_CONTEXT_NOT_CONFIGURED",
    "Channel",
    "KnowledgeContext",
    "KnowledgeEntry",
    "KnowledgeInvalidError",
    "KnowledgePack",
    "build_knowledge_pack",
    "knowledge_invalid_error",
    "select_knowledge_context",
]
