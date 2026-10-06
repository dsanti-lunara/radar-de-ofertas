"""Publication lifecycle, publisher port and publication policy (RDR-020, RDR-072).

``docs/03_DOMAIN_MODEL.md`` makes ``Publication`` its own entity, separate from
``ContentGeneration`` and ``Opportunity`` (AUT-025, AUT-034), and models the send
as a *side effect* (AUT-132). This module implements the framework-free core of
that slice (AUT-397):

* the :class:`Publication` lifecycle (``DRAFT``/``READY``/``PUBLISHING``/
  ``PUBLISHED``/``UPDATED``/``EXPIRED``/``FAILED``/``DELETED``) and its
  append-only :class:`PublicationEvent` history (``docs/09_PUBLISHING.md``);
* the narrow :class:`Publisher` port so the deterministic Fake is used offline
  and the real Telegram/WhatsApp publishers stay in their own tickets
  (RDR-068/RDR-071/RDR-108, AUT-359, AUT-421);
* the versioned, hashed :class:`PublicationPolicy` that freezes the approved
  reference limits (hard cap ``12``/day/brand, burst ``2`` posts per ``15``
  minutes) and exposes cooldown/quiet hours as explicit configuration instead of
  inventing values the SDD does not calibrate (AUT-045, AUT-175, AUT-176);
* :func:`evaluate_publication_policy` and :func:`decide_publication_gate`, the
  deterministic gates that block **before** the publisher is ever called.

A confirmed send is idempotent by ``idempotency_key`` (AUT-039, AUT-132,
AUT-184): repeating the same key never duplicates a confirmed send. The
unknown-result window is deliberately *not* handled here; it belongs to
``adr/0001-unknown-publication-result.md`` and TKT-24. No AI, HTTP, SQLAlchemy or
browser code lives in this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from radar.domain.capture import (
    IdFactory,
    default_id_factory,
    find_sensitive_fields,
)
from radar.domain.errors import RadarError, RadarException
from radar.domain.knowledge import Channel
from radar.domain.schedule import DEFAULT_SCHEDULE_TIMEZONE, QuietWindow
from radar.domain.taxonomy import Brand

#: Version of the public Publication contract (``docs/04_DATA_CONTRACTS.md``).
PUBLICATION_SCHEMA_VERSION = "1.0"

#: Version of the publication policy document schema.
PUBLICATION_POLICY_SCHEMA_VERSION = "1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
PUBLICATION_INPUT_INVALID = "RAD-PUB-001"
PUBLICATION_NOT_FOUND = "RAD-PUB-002"
PUBLICATION_BLOCKED = "RAD-PUB-003"
PUBLICATION_PUBLISHER_UNAVAILABLE = "RAD-PUB-004"
PUBLICATION_PUBLISHER_INVALID = "RAD-PUB-005"
#: The remote result of a send is unknown (crash/timeout after acceptance): the
#: publication is suspended and a HumanAction opens; never a confirmed failure.
PUBLICATION_RESULT_UNKNOWN = "RAD-PUB-006"
#: A human resolution of an unknown result lacks sufficient evidence.
PUBLICATION_RESOLUTION_BLOCKED = "RAD-PUB-007"
PUBLICATION_POLICY_INVALID = "RAD-CFG-016"

#: Entity type recorded on the Publication audit event.
ENTITY_PUBLICATION = "publication"

#: Provenance source recorded on the Publication audit event.
AUDIT_SOURCE_PUBLICATION = "publishing"

#: Deterministic reason codes returned by the publication gates (safe to persist).
REASON_ALLOWED = "ALLOWED"
REASON_QUIET_HOURS = "QUIET_HOURS"
REASON_COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
REASON_BURST_LIMIT = "BURST_LIMIT"
REASON_HARD_CAP_REACHED = "HARD_CAP_REACHED"

#: Reason a stale content preview must be revalidated before the publisher.
REASON_REVALIDATION_REQUIRED = "REVALIDATION_REQUIRED"

#: Reason an unknown send result suspends the publication (GRILL-002, ADR 0001).
REASON_SEND_RESULT_UNKNOWN = "SEND_RESULT_UNKNOWN"

#: Reasons the authorization/compliance gate can block a publication.
REASON_AUTHORIZATION_BLOCKED = "AUTHORIZATION_BLOCKED"

#: Approved reference limits of ``docs/09_PUBLISHING.md``.
APPROVED_HARD_CAP_PER_DAY = 12
APPROVED_BURST_LIMIT = 2
APPROVED_BURST_WINDOW_MINUTES = 15

#: Fields accepted from a publisher response; anything else fails closed.
_ALLOWED_PUBLISHER_FIELDS = frozenset({"external_message_id"})

#: Fields the domain reads from a mapping publication policy.
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class PublicationStatus(StrEnum):
    """Lifecycle status of a Publication (``docs/09_PUBLISHING.md``).

    ``UNKNOWN`` is the suspended state of an unconfirmed remote send: the send may
    have been accepted but lacks sufficient local confirmation, so the publication
    is suspended pending human review and is never auto-resent (GRILL-002,
    ``adr/0001-unknown-publication-result.md``).
    """

    DRAFT = "DRAFT"
    READY = "READY"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    UPDATED = "UPDATED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    DELETED = "DELETED"


class PublicationEventType(StrEnum):
    """Append-only Publication events (``docs/03_DOMAIN_MODEL.md``)."""

    CREATED = "CREATED"
    PUBLISHED = "PUBLISHED"
    PRICE_CHANGED = "PRICE_CHANGED"
    EXPIRED = "EXPIRED"
    MESSAGE_EDITED = "MESSAGE_EDITED"
    LINK_INVALID = "LINK_INVALID"
    ERROR = "ERROR"
    #: The remote result could not be confirmed (suspension, ADR 0001).
    RESULT_UNKNOWN = "RESULT_UNKNOWN"
    #: A human resolution of an unknown result was recorded (evidence audited).
    RESOLVED = "RESOLVED"


class PublicationError(RadarException):
    """Raised when a Publication cannot be produced safely."""


def _error(
    code: str,
    message: str,
    *,
    retryable: bool,
    action: str,
    context: Mapping[str, Any] | None = None,
) -> PublicationError:
    return PublicationError(
        RadarError(
            code=code,
            message=message,
            retryable=retryable,
            action=action,
            context=dict(context or {}),
        )
    )


def publication_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> PublicationError:
    """Build the structured ``RAD-PUB-001`` error for invalid publication input."""

    return _error(
        PUBLICATION_INPUT_INVALID,
        message,
        retryable=False,
        action="Corrigir o input de publicação e enviar novamente",
        context=context,
    )


def publication_not_found_error(publication_id: str) -> PublicationError:
    """Build the structured ``RAD-PUB-002`` not-found error."""

    return _error(
        PUBLICATION_NOT_FOUND,
        "Publication não encontrada",
        retryable=False,
        action="Verificar o publication_id informado",
        context={"publication_id": publication_id},
    )


def publication_blocked_error(
    *, reason_code: str, message: str, context: Mapping[str, Any] | None = None
) -> PublicationError:
    """Build the structured ``RAD-PUB-003`` error for a pre-publisher block.

    The block is a legitimate domain outcome (SHADOW, compliance, cap/burst/
    cooldown/quiet hours): it is deterministic, not retryable by itself and
    carries the actionable ``reason_code`` in the context.
    """

    return _error(
        PUBLICATION_BLOCKED,
        message,
        retryable=False,
        action="Resolver o bloqueio vigente antes de tentar publicar novamente",
        context={"reason_code": reason_code, **dict(context or {})},
    )


class PublicationResultUnknown(PublicationError):
    """Raised when a send may have been accepted remotely without confirmation.

    The result is *unknown*, never a confirmed failure: the publication is
    suspended, a HumanAction is opened and no automatic resend is allowed
    (GRILL-002, ADR 0001). This is distinct from
    :data:`PUBLICATION_PUBLISHER_UNAVAILABLE`, which is a confirmed failure.
    """


def publication_result_unknown_error(
    message: str = "Resultado do envio desconhecido; publicação suspensa para revisão humana",
    *,
    context: Mapping[str, Any] | None = None,
) -> PublicationResultUnknown:
    """Build the structured ``RAD-PUB-006`` unknown-result error."""

    return PublicationResultUnknown(
        RadarError(
            code=PUBLICATION_RESULT_UNKNOWN,
            message=message,
            retryable=False,
            action=(
                "Coletar evidência suficiente e resolver o resultado desconhecido; "
                "não reenviar automaticamente"
            ),
            context={"reason_code": REASON_SEND_RESULT_UNKNOWN, **dict(context or {})},
        )
    )


def publication_resolution_blocked_error(
    message: str,
    *,
    context: Mapping[str, Any] | None = None,
) -> PublicationError:
    """Build the structured ``RAD-PUB-007`` error for an evidence-less resolution."""

    return _error(
        PUBLICATION_RESOLUTION_BLOCKED,
        message,
        retryable=False,
        action=(
            "Registrar evidência suficiente (marcador externo, recibo do provider ou "
            "auditoria do destino) antes de concluir o envio ou liberar nova tentativa"
        ),
        context=dict(context or {}),
    )


def publication_publisher_unavailable_error(
    *, context: Mapping[str, Any] | None = None
) -> PublicationError:
    """Build the retryable ``RAD-PUB-004`` error for an unavailable publisher."""

    return _error(
        PUBLICATION_PUBLISHER_UNAVAILABLE,
        "Publisher indisponível",
        retryable=True,
        action="Repetir o envio quando o publisher estiver disponível",
        context=context,
    )


def publication_publisher_invalid_error(
    *, provider: str, context: Mapping[str, Any] | None = None
) -> PublicationError:
    """Build the ``RAD-PUB-005`` error for an invalid publisher response."""

    return _error(
        PUBLICATION_PUBLISHER_INVALID,
        "Resposta do publisher inválida",
        retryable=False,
        action="Descartar a resposta e revisar o publisher",
        context={"provider": provider, **dict(context or {})},
    )


def publication_policy_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> PublicationError:
    """Build the structured ``RAD-CFG-016`` error for an invalid policy."""

    return _error(
        PUBLICATION_POLICY_INVALID,
        message,
        retryable=False,
        action="Corrigir o arquivo de publication policy e validar novamente",
        context=context,
    )


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _content_hash(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prepared_content_hash(
    *,
    content_text: str,
    affiliate_url: str,
    price: str,
    destination_id: str,
    channel: Channel,
) -> str:
    """Return the canonical hash of the content effectively prepared for a send.

    The receipt records this hash so the content that was actually prepared can be
    compared with the approved preview; it never proves delivery or read
    (``docs/09_PUBLISHING.md``).
    """

    return _content_hash(
        {
            "content_text": content_text,
            "affiliate_url": affiliate_url,
            "price": price,
            "destination_id": destination_id,
            "channel": channel.value,
        }
    )


@dataclass(frozen=True, slots=True)
class PublicationLimits:
    """Effective limits for one channel slice (``docs/09_PUBLISHING.md``).

    ``cooldown_minutes`` is ``None`` when the SDD does not calibrate a cooldown:
    the baseline reports the gap explicitly instead of inventing a value.
    """

    hard_cap_per_day: int
    burst_limit: int
    burst_window_minutes: int
    cooldown_minutes: int | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "hard_cap_per_day": self.hard_cap_per_day,
            "burst_limit": self.burst_limit,
            "burst_window_minutes": self.burst_window_minutes,
            "cooldown_minutes": self.cooldown_minutes,
        }


def _parse_positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise publication_policy_invalid_error(
            f"{field_name} deve ser um inteiro maior que zero",
            context={"field": field_name},
        )
    return value


def _parse_optional_positive_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    return _parse_positive_int(value, field_name=field_name)


def _parse_days(value: object) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise publication_policy_invalid_error(
            "days deve ser uma lista de inteiros 0..6", context={"field": "days"}
        )
    days: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not (0 <= item <= 6):
            raise publication_policy_invalid_error(
                "days deve ser uma lista de inteiros 0..6", context={"field": "days"}
            )
        if item not in days:
            days.append(item)
    return tuple(sorted(days))


def _parse_quiet_window(value: object) -> QuietWindow:
    if isinstance(value, QuietWindow):
        return value
    if not isinstance(value, Mapping):
        raise publication_policy_invalid_error(
            "quiet_window deve ser um objeto", context={"field": "quiet_windows"}
        )
    start = value.get("start")
    end = value.get("end")
    if not isinstance(start, str) or not _HHMM.match(start):
        raise publication_policy_invalid_error(
            "quiet_window.start deve seguir HH:MM", context={"field": "quiet_window.start"}
        )
    if not isinstance(end, str) or not _HHMM.match(end):
        raise publication_policy_invalid_error(
            "quiet_window.end deve seguir HH:MM", context={"field": "quiet_window.end"}
        )
    if start == end:
        raise publication_policy_invalid_error(
            "quiet_window.start e end não podem ser iguais", context={"field": "quiet_windows"}
        )
    return QuietWindow(start=start, end=end, days=_parse_days(value.get("days")))


def _parse_quiet_windows(value: object) -> tuple[QuietWindow, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise publication_policy_invalid_error(
            "quiet_windows deve ser uma lista", context={"field": "quiet_windows"}
        )
    return tuple(_parse_quiet_window(item) for item in value)


def _parse_timezone(value: object) -> str:
    if value is None:
        return DEFAULT_SCHEDULE_TIMEZONE
    if not isinstance(value, str) or not value.strip():
        raise publication_policy_invalid_error(
            "timezone deve ser texto IANA", context={"field": "timezone"}
        )
    cleaned = value.strip()
    try:
        ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise publication_policy_invalid_error(
            "timezone inválido", context={"field": "timezone", "value": cleaned}
        ) from exc
    return cleaned


def _build_limits(
    document: Mapping[str, Any], *, default: PublicationLimits | None
) -> PublicationLimits:
    fallback = default or PublicationLimits(
        hard_cap_per_day=APPROVED_HARD_CAP_PER_DAY,
        burst_limit=APPROVED_BURST_LIMIT,
        burst_window_minutes=APPROVED_BURST_WINDOW_MINUTES,
    )
    return PublicationLimits(
        hard_cap_per_day=_parse_positive_int(
            document.get("hard_cap_per_day", fallback.hard_cap_per_day),
            field_name="hard_cap_per_day",
        ),
        burst_limit=_parse_positive_int(
            document.get("burst_limit", fallback.burst_limit), field_name="burst_limit"
        ),
        burst_window_minutes=_parse_positive_int(
            document.get("burst_window_minutes", fallback.burst_window_minutes),
            field_name="burst_window_minutes",
        ),
        cooldown_minutes=_parse_optional_positive_int(
            document.get("cooldown_minutes", fallback.cooldown_minutes),
            field_name="cooldown_minutes",
        ),
    )


def _validate_not_looser(
    *, channel: str, override: PublicationLimits, default: PublicationLimits
) -> None:
    """Refuse a channel override that loosens the approved threshold.

    ``docs/09_PUBLISHING.md`` requires WhatsApp to be at least as strict as the
    default/Telegram limits; a looser channel override fails closed instead of
    silently granting more autonomy.
    """

    if override.hard_cap_per_day > default.hard_cap_per_day:
        raise publication_policy_invalid_error(
            "channel override não pode afrouxar o hard cap",
            context={"channel": channel, "field": "hard_cap_per_day"},
        )
    if override.burst_limit > default.burst_limit:
        raise publication_policy_invalid_error(
            "channel override não pode afrouxar o burst",
            context={"channel": channel, "field": "burst_limit"},
        )
    if override.burst_window_minutes < default.burst_window_minutes:
        raise publication_policy_invalid_error(
            "channel override não pode encurtar a janela de burst",
            context={"channel": channel, "field": "burst_window_minutes"},
        )
    if default.cooldown_minutes is not None and (
        override.cooldown_minutes is None or override.cooldown_minutes < default.cooldown_minutes
    ):
        raise publication_policy_invalid_error(
            "channel override não pode afrouxar o cooldown",
            context={"channel": channel, "field": "cooldown_minutes"},
        )


@dataclass(frozen=True, slots=True)
class PublicationPolicy:
    """Versioned, hashed publication policy (AUT-045, AUT-175, AUT-176)."""

    policy_version: str
    content_hash: str
    timezone: str = DEFAULT_SCHEDULE_TIMEZONE
    default_limits: PublicationLimits = field(
        default_factory=lambda: PublicationLimits(
            hard_cap_per_day=APPROVED_HARD_CAP_PER_DAY,
            burst_limit=APPROVED_BURST_LIMIT,
            burst_window_minutes=APPROVED_BURST_WINDOW_MINUTES,
        )
    )
    channel_limits: Mapping[str, PublicationLimits] = field(default_factory=dict)
    quiet_windows: tuple[QuietWindow, ...] = ()

    def limits_for(self, channel: Channel) -> PublicationLimits:
        """Return the effective limits for ``channel`` (override or default)."""

        return self.channel_limits.get(channel.value, self.default_limits)

    def is_quiet(self, now: datetime) -> bool:
        """True when ``now`` falls in one of the policy quiet windows (AUT-143)."""

        if not self.quiet_windows:
            return False
        local = _to_utc(now).astimezone(ZoneInfo(self.timezone))
        return any(window.contains(local) for window in self.quiet_windows)

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLICATION_POLICY_SCHEMA_VERSION,
            "policy_version": self.policy_version,
            "policy_hash": self.content_hash,
            "timezone": self.timezone,
            "default_limits": self.default_limits.to_contract(),
            "channel_limits": {
                name: limits.to_contract() for name, limits in sorted(self.channel_limits.items())
            },
            "quiet_windows": [window.to_contract() for window in self.quiet_windows],
        }


def build_publication_policy(document: Mapping[str, Any]) -> PublicationPolicy:
    """Build and validate the publication policy from a plain document.

    A missing ``hard_cap_per_day``/``burst_limit``/``burst_window_minutes`` keeps
    the approved reference values; ``cooldown_minutes``/``quiet_windows`` stay
    explicitly absent when not configured (the SDD does not calibrate them). An
    unsupported ``schema_version``, a non-positive limit, an invalid timezone, an
    invalid quiet window or a channel override that loosens the threshold fails
    closed with ``RAD-CFG-016``.
    """

    if not isinstance(document, Mapping):
        raise publication_policy_invalid_error("Policy deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != PUBLICATION_POLICY_SCHEMA_VERSION:
        raise publication_policy_invalid_error(
            "schema_version de publication policy não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("policy_version") or "").strip()
    if not version:
        raise publication_policy_invalid_error("policy_version é obrigatório")

    timezone = _parse_timezone(document.get("timezone"))
    default_limits = _build_limits(document, default=None)
    quiet_windows = _parse_quiet_windows(document.get("quiet_windows"))

    raw_channels = document.get("channels")
    if raw_channels is None:
        raw_channels = {}
    if not isinstance(raw_channels, Mapping):
        raise publication_policy_invalid_error(
            "channels deve ser um objeto", context={"field": "channels"}
        )

    channel_limits: dict[str, PublicationLimits] = {}
    for raw_name, raw_limits in raw_channels.items():
        name = str(raw_name)
        if name not in {channel.value for channel in Channel}:
            raise publication_policy_invalid_error(
                "canal desconhecido em channels", context={"channel": name}
            )
        if not isinstance(raw_limits, Mapping):
            raise publication_policy_invalid_error(
                "limits de canal deve ser um objeto", context={"channel": name}
            )
        override = _build_limits(raw_limits, default=default_limits)
        _validate_not_looser(channel=name, override=override, default=default_limits)
        channel_limits[name] = override

    normalized = {
        "schema_version": PUBLICATION_POLICY_SCHEMA_VERSION,
        "policy_version": version,
        "timezone": timezone,
        "default_limits": default_limits.to_contract(),
        "channel_limits": {
            name: limits.to_contract() for name, limits in sorted(channel_limits.items())
        },
        "quiet_windows": [window.to_contract() for window in quiet_windows],
    }
    return PublicationPolicy(
        policy_version=version,
        content_hash=_content_hash(normalized),
        timezone=timezone,
        default_limits=default_limits,
        channel_limits=channel_limits,
        quiet_windows=quiet_windows,
    )


#: Approved baseline: the reference limits of ``docs/09_PUBLISHING.md``; no
#: cooldown/quiet window is invented (both are explicit configuration gaps).
APPROVED_PUBLICATION_POLICY_DOCUMENT: dict[str, Any] = {
    "schema_version": PUBLICATION_POLICY_SCHEMA_VERSION,
    "policy_version": "publication-policy-1.0",
    "timezone": DEFAULT_SCHEDULE_TIMEZONE,
    "hard_cap_per_day": APPROVED_HARD_CAP_PER_DAY,
    "burst_limit": APPROVED_BURST_LIMIT,
    "burst_window_minutes": APPROVED_BURST_WINDOW_MINUTES,
}

#: The approved baseline publication policy.
APPROVED_PUBLICATION_POLICY = build_publication_policy(APPROVED_PUBLICATION_POLICY_DOCUMENT)


_REASON_MESSAGES: dict[str, str] = {
    REASON_ALLOWED: "Publicação permitida pela policy vigente",
    REASON_QUIET_HOURS: "Horário silencioso vigente: publicação pausada, discovery continua",
    REASON_COOLDOWN_ACTIVE: "Cooldown ativo para o destino; aguardar a janela antes de publicar",
    REASON_BURST_LIMIT: "Burst do canal atingido; aguardar a janela antes de publicar",
    REASON_HARD_CAP_REACHED: "Hard cap diário por marca atingido; cap não é meta",
}


@dataclass(frozen=True, slots=True)
class PublicationPolicyDecision:
    """Observable result of the publication policy gate (RDR-020)."""

    allowed: bool
    reason_code: str
    message: str
    channel: Channel
    brand: Brand
    destination_id: str
    limits: PublicationLimits
    hard_cap_count: int
    burst_count: int
    policy_version: str
    policy_hash: str
    decided_at: datetime

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLICATION_SCHEMA_VERSION,
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "message": self.message,
            "channel": self.channel.value,
            "brand": self.brand.value,
            "destination_id": self.destination_id,
            "limits": self.limits.to_contract(),
            "hard_cap_count": self.hard_cap_count,
            "burst_count": self.burst_count,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "decided_at": _to_utc(self.decided_at).isoformat(),
        }


def _published_at(publication: Publication) -> datetime | None:
    if publication.status is not PublicationStatus.PUBLISHED:
        return None
    return None if publication.published_at is None else _to_utc(publication.published_at)


def evaluate_publication_policy(
    policy: PublicationPolicy,
    *,
    brand: Brand,
    channel: Channel,
    destination_id: str,
    now: datetime,
    publications: Sequence[Publication],
) -> PublicationPolicyDecision:
    """Apply cap/burst/cooldown/quiet hours deterministically (AUT-175/AUT-176).

    Quiet hours, the per-brand hard cap, the per-brand/channel burst and the
    per-destination cooldown are evaluated from the persisted confirmed
    publications; a blocked decision never reaches the publisher.
    """

    reference = _to_utc(now)
    limits = policy.limits_for(channel)
    day_start = reference - timedelta(hours=24)
    hard_cap_count = sum(
        1
        for item in publications
        if item.brand is brand
        and (moment := _published_at(item)) is not None
        and moment >= day_start
    )
    burst_start = reference - timedelta(minutes=limits.burst_window_minutes)
    burst_count = sum(
        1
        for item in publications
        if item.brand is brand
        and item.channel is channel
        and (moment := _published_at(item)) is not None
        and moment >= burst_start
    )

    def decision(allowed: bool, reason_code: str) -> PublicationPolicyDecision:
        return PublicationPolicyDecision(
            allowed=allowed,
            reason_code=reason_code,
            message=_REASON_MESSAGES.get(reason_code, "Publicação bloqueada pela policy vigente"),
            channel=channel,
            brand=brand,
            destination_id=destination_id,
            limits=limits,
            hard_cap_count=hard_cap_count,
            burst_count=burst_count,
            policy_version=policy.policy_version,
            policy_hash=policy.content_hash,
            decided_at=reference,
        )

    if policy.is_quiet(reference):
        return decision(False, REASON_QUIET_HOURS)

    if hard_cap_count >= limits.hard_cap_per_day:
        return decision(False, REASON_HARD_CAP_REACHED)

    if burst_count >= limits.burst_limit:
        return decision(False, REASON_BURST_LIMIT)

    if limits.cooldown_minutes is not None:
        cooldown_start = reference - timedelta(minutes=limits.cooldown_minutes)
        for item in publications:
            if item.destination_id != destination_id:
                continue
            moment = _published_at(item)
            if moment is not None and moment >= cooldown_start:
                return decision(False, REASON_COOLDOWN_ACTIVE)

    return decision(True, REASON_ALLOWED)


@dataclass(frozen=True, slots=True)
class PublicationSendRequest:
    """The narrow request handed to a :class:`Publisher` (RDR-071/RDR-108)."""

    publication_id: str
    idempotency_key: str
    channel: Channel
    destination_id: str
    content_text: str
    affiliate_url: str
    correlation_id: str


@runtime_checkable
class Publisher(Protocol):
    """Contract every publisher (Fake first) must satisfy.

    The publisher isolates the external call and returns a raw structured mapping
    that the domain validates before anything is persisted. A publisher must
    respect the ``idempotency_key`` and never invent a commercial message.
    """

    @property
    def name(self) -> str: ...

    def send(self, request: PublicationSendRequest) -> Mapping[str, Any]: ...


def parse_publisher_response(raw: object, *, provider: str) -> str:
    """Validate a publisher response and return the external message id.

    A non-mapping response, a sensitive/unknown field or a missing/blank
    ``external_message_id`` fails closed with ``RAD-PUB-005``; the receipt is
    evidence of an *observed send*, never a delivery/read promise.
    """

    if not isinstance(raw, Mapping):
        raise publication_publisher_invalid_error(provider=provider)
    sensitive = find_sensitive_fields(raw)
    if sensitive:
        raise publication_publisher_invalid_error(
            provider=provider, context={"fields": list(sensitive)}
        )
    unknown = sorted({str(key) for key in raw} - _ALLOWED_PUBLISHER_FIELDS)
    if unknown:
        raise publication_publisher_invalid_error(provider=provider, context={"fields": unknown})
    external_message_id = raw.get("external_message_id")
    if not isinstance(external_message_id, str) or not external_message_id.strip():
        raise publication_publisher_invalid_error(
            provider=provider, context={"field": "external_message_id"}
        )
    return external_message_id.strip()


@dataclass(frozen=True, slots=True)
class PublicationEvent:
    """One append-only event of the Publication lifecycle (RDR-020)."""

    event_id: str
    publication_id: str
    event_type: PublicationEventType
    occurred_at: datetime
    correlation_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = PUBLICATION_SCHEMA_VERSION

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "publication_id": self.publication_id,
            "event_type": self.event_type.value,
            "occurred_at": _to_utc(self.occurred_at).isoformat(),
            "correlation_id": self.correlation_id,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class Publication:
    """Side effect of sending one validated ContentGeneration (RDR-020).

    It is a distinct entity from ``ContentGeneration`` and ``Opportunity``
    (AUT-025, AUT-034): it references both and adds the destination, the
    confirmed ``external_message_id``, the ``published_price`` and the
    ``idempotency_key`` that makes a repeated send a no-op (AUT-039, AUT-184).
    """

    publication_id: str
    opportunity_id: str
    content_generation_id: str
    affiliate_link_id: str
    brand: Brand
    channel: Channel
    destination_id: str
    idempotency_key: str
    revision: int
    status: PublicationStatus
    external_message_id: str | None
    published_price: str | None
    correlation_id: str
    audit_event_id: str
    created_at: datetime
    published_at: datetime | None
    schema_version: str = PUBLICATION_SCHEMA_VERSION
    events: tuple[PublicationEvent, ...] = ()

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "publication_id": self.publication_id,
            "opportunity_id": self.opportunity_id,
            "content_generation_id": self.content_generation_id,
            "affiliate_link_id": self.affiliate_link_id,
            "brand": self.brand.value,
            "channel": self.channel.value,
            "destination_id": self.destination_id,
            "external_message_id": self.external_message_id,
            "published_price": self.published_price,
            "revision": self.revision,
            "idempotency_key": self.idempotency_key,
            "correlation_id": self.correlation_id,
            "audit_event_id": self.audit_event_id,
            "created_at": _to_utc(self.created_at).isoformat(),
            "published_at": (
                None if self.published_at is None else _to_utc(self.published_at).isoformat()
            ),
            "events": [event.to_contract() for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class PublicationResolution:
    """Outcome of a publication request (RDR-020/RDR-072).

    ``idempotent_replay`` is ``True`` when a previously confirmed publication was
    returned for the same ``idempotency_key`` without a second send.
    """

    publication: Publication
    idempotent_replay: bool

    def to_contract(self) -> dict[str, Any]:
        payload = self.publication.to_contract()
        payload["idempotent_replay"] = self.idempotent_replay
        return payload


def build_publication(
    *,
    opportunity_id: str,
    content_generation_id: str,
    affiliate_link_id: str,
    brand: Brand,
    channel: Channel,
    destination_id: str,
    idempotency_key: str,
    published_price: str,
    external_message_id: str,
    correlation_id: str,
    audit_event_id: str,
    created_at: datetime,
    published_at: datetime,
    revision: int = 1,
    publication_id: object | None = None,
    schema_version: object = PUBLICATION_SCHEMA_VERSION,
    id_factory: IdFactory = default_id_factory,
) -> Publication:
    """Assemble a confirmed ``PUBLISHED`` Publication with its event history."""

    if str(schema_version) != PUBLICATION_SCHEMA_VERSION:
        raise publication_input_invalid_error(
            "schema_version de Publication não suportada",
            context={"supported": PUBLICATION_SCHEMA_VERSION},
        )
    if not isinstance(brand, Brand):
        raise publication_input_invalid_error(
            "brand inválida para a Publication",
            context={"field": "brand"},
        )
    if not isinstance(channel, Channel):
        raise publication_input_invalid_error(
            "channel inválido para a Publication",
            context={"field": "channel"},
        )
    resolved_id = str(id_factory("pub")) if publication_id is None else str(publication_id).strip()
    created = _to_utc(created_at)
    published = _to_utc(published_at)
    events = (
        PublicationEvent(
            event_id=str(id_factory("pev")),
            publication_id=resolved_id,
            event_type=PublicationEventType.CREATED,
            occurred_at=created,
            correlation_id=correlation_id,
            payload={"status": PublicationStatus.READY.value},
        ),
        PublicationEvent(
            event_id=str(id_factory("pev")),
            publication_id=resolved_id,
            event_type=PublicationEventType.PUBLISHED,
            occurred_at=published,
            correlation_id=correlation_id,
            payload={
                "external_message_id": external_message_id,
                "destination_id": destination_id,
                "channel": channel.value,
            },
        ),
    )
    return Publication(
        publication_id=resolved_id,
        opportunity_id=opportunity_id,
        content_generation_id=content_generation_id,
        affiliate_link_id=affiliate_link_id,
        brand=brand,
        channel=channel,
        destination_id=destination_id,
        idempotency_key=idempotency_key,
        revision=revision,
        status=PublicationStatus.PUBLISHED,
        external_message_id=external_message_id,
        published_price=published_price,
        correlation_id=correlation_id,
        audit_event_id=audit_event_id,
        created_at=created,
        published_at=published,
        events=events,
    )


def build_suspended_publication(
    *,
    opportunity_id: str,
    content_generation_id: str,
    affiliate_link_id: str,
    brand: Brand,
    channel: Channel,
    destination_id: str,
    idempotency_key: str,
    published_price: str,
    content_hash: str,
    correlation_id: str,
    audit_event_id: str,
    created_at: datetime,
    revision: int = 1,
    publication_id: object | None = None,
    schema_version: object = PUBLICATION_SCHEMA_VERSION,
    id_factory: IdFactory = default_id_factory,
) -> Publication:
    """Assemble a suspended ``UNKNOWN`` Publication with its receipt event.

    The send may have been accepted but lacks sufficient confirmation. The
    publication is persisted suspended with a receipt anchor (destination,
    revision, prepared content hash, Correlation ID, observed_at, external marker
    when available) so dedupe/audit survive the absence/expiry of the external
    evidence and no automatic resend happens (GRILL-002, ADR 0001).
    """

    if str(schema_version) != PUBLICATION_SCHEMA_VERSION:
        raise publication_input_invalid_error(
            "schema_version de Publication não suportada",
            context={"supported": PUBLICATION_SCHEMA_VERSION},
        )
    if not isinstance(brand, Brand):
        raise publication_input_invalid_error(
            "brand inválida para a Publication",
            context={"field": "brand"},
        )
    if not isinstance(channel, Channel):
        raise publication_input_invalid_error(
            "channel inválido para a Publication",
            context={"field": "channel"},
        )
    resolved_id = str(id_factory("pub")) if publication_id is None else str(publication_id).strip()
    created = _to_utc(created_at)
    events = (
        PublicationEvent(
            event_id=str(id_factory("pev")),
            publication_id=resolved_id,
            event_type=PublicationEventType.CREATED,
            occurred_at=created,
            correlation_id=correlation_id,
            payload={"status": PublicationStatus.READY.value},
        ),
        PublicationEvent(
            event_id=str(id_factory("pev")),
            publication_id=resolved_id,
            event_type=PublicationEventType.RESULT_UNKNOWN,
            occurred_at=created,
            correlation_id=correlation_id,
            payload={
                "reason_code": REASON_SEND_RESULT_UNKNOWN,
                "destination_id": destination_id,
                "channel": channel.value,
                "revision": revision,
                "content_hash": content_hash,
                "external_message_id": None,
                "observed_at": created.isoformat(),
            },
        ),
    )
    return Publication(
        publication_id=resolved_id,
        opportunity_id=opportunity_id,
        content_generation_id=content_generation_id,
        affiliate_link_id=affiliate_link_id,
        brand=brand,
        channel=channel,
        destination_id=destination_id,
        idempotency_key=idempotency_key,
        revision=revision,
        status=PublicationStatus.UNKNOWN,
        external_message_id=None,
        published_price=published_price,
        correlation_id=correlation_id,
        audit_event_id=audit_event_id,
        created_at=created,
        published_at=None,
        events=events,
    )


__all__ = [
    "APPROVED_BURST_LIMIT",
    "APPROVED_BURST_WINDOW_MINUTES",
    "APPROVED_HARD_CAP_PER_DAY",
    "APPROVED_PUBLICATION_POLICY",
    "APPROVED_PUBLICATION_POLICY_DOCUMENT",
    "AUDIT_SOURCE_PUBLICATION",
    "ENTITY_PUBLICATION",
    "PUBLICATION_BLOCKED",
    "PUBLICATION_INPUT_INVALID",
    "PUBLICATION_NOT_FOUND",
    "PUBLICATION_POLICY_INVALID",
    "PUBLICATION_POLICY_SCHEMA_VERSION",
    "PUBLICATION_PUBLISHER_INVALID",
    "PUBLICATION_PUBLISHER_UNAVAILABLE",
    "PUBLICATION_RESOLUTION_BLOCKED",
    "PUBLICATION_RESULT_UNKNOWN",
    "PUBLICATION_SCHEMA_VERSION",
    "REASON_ALLOWED",
    "REASON_AUTHORIZATION_BLOCKED",
    "REASON_BURST_LIMIT",
    "REASON_COOLDOWN_ACTIVE",
    "REASON_HARD_CAP_REACHED",
    "REASON_QUIET_HOURS",
    "REASON_REVALIDATION_REQUIRED",
    "REASON_SEND_RESULT_UNKNOWN",
    "Publication",
    "PublicationError",
    "PublicationEvent",
    "PublicationEventType",
    "PublicationLimits",
    "PublicationPolicy",
    "PublicationPolicyDecision",
    "PublicationResolution",
    "PublicationResultUnknown",
    "PublicationSendRequest",
    "PublicationStatus",
    "Publisher",
    "build_publication",
    "build_publication_policy",
    "build_suspended_publication",
    "evaluate_publication_policy",
    "parse_publisher_response",
    "prepared_content_hash",
    "publication_blocked_error",
    "publication_input_invalid_error",
    "publication_not_found_error",
    "publication_policy_invalid_error",
    "publication_publisher_invalid_error",
    "publication_publisher_unavailable_error",
    "publication_resolution_blocked_error",
    "publication_result_unknown_error",
]
