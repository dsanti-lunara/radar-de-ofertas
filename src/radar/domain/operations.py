"""Autonomy policy, operational modes and external-action kill switch.

This module implements the framework-free core of the operational controls of
``docs/08_WORKFLOW_ENGINE.md`` (RDR-043) and the integration health model of
``docs/11_OPERATIONS_AND_UI.md`` / ``docs/12_SECURITY_AND_COMPLIANCE.md``
(RDR-044):

* :class:`AutomationMode` (``MANUAL``/``SHADOW``/``ASSISTED``/``AUTO``) is an
  independent level of automation that may vary by brand, marketplace, channel and
  capability (AUT-127, AUT-128); it is resolved from a versioned, hashed policy
  and never hardcoded (AUT-045, AUT-059);
* :class:`GlobalMode` (``RUNNING``/``PAUSED``/``DRAINING``/``MAINTENANCE``) is the
  global state of the Radar Core (AUT-149, AUT-228);
* :class:`ChannelCompliancePolicy` is a versioned, blocking policy with an explicit
  status/review window; an ``UNKNOWN``/expired policy never releases an external
  side effect, even with human approval (AUT-293, AUT-294, AUT-295);
* :class:`IntegrationHealth` records the standardized external states so one
  unhealthy integration isolates its own scope instead of the whole node
  (AUT-139, AUT-315);
* :func:`decide_external_action` is the single authorization gate that turns
  ``mode/policy/operator command`` into permission or block and keeps
  reading/diagnostic/recovery available under ``STOP_EXTERNAL_ACTIONS``
  (AUT-317, GRILL-001).

The module is deliberately side-effect free and framework-free (no
FastAPI/SQLAlchemy/Chrome) so the domain stays independent from infrastructure
(AUT-397). It never calls AI and never creates an affiliate link (AUT-031,
AUT-164).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from radar.domain.errors import RadarError, RadarException
from radar.domain.taxonomy import Brand

#: Version of the public operations contract (``docs/04_DATA_CONTRACTS.md``).
OPERATIONS_SCHEMA_VERSION = "1.0"

#: Version of the automation policy document schema.
AUTOMATION_POLICY_SCHEMA_VERSION = "1.0"

#: Version of the channel compliance policy document schema.
COMPLIANCE_POLICY_SCHEMA_VERSION = "1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
OPERATIONS_INPUT_INVALID = "RAD-WF-018"
AUTOMATION_POLICY_INVALID = "RAD-CFG-012"
COMPLIANCE_POLICY_INVALID = "RAD-CFG-013"

#: Decision reason codes (stable, actionable and safe to persist).
REASON_ALLOWED = "ALLOWED"
REASON_MANUAL_MODE = "MANUAL_MODE"
REASON_SHADOW_NO_COMMERCIAL_SEND = "SHADOW_NO_COMMERCIAL_SEND"
REASON_PUBLICATION_APPROVAL_REQUIRED = "PUBLICATION_APPROVAL_REQUIRED"
REASON_STOP_EXTERNAL_ACTIONS = "STOP_EXTERNAL_ACTIONS"
REASON_GLOBAL_MODE_PAUSED = "GLOBAL_MODE_PAUSED"
REASON_GLOBAL_MODE_DRAINING = "GLOBAL_MODE_DRAINING"
REASON_GLOBAL_MODE_MAINTENANCE = "GLOBAL_MODE_MAINTENANCE"
REASON_POLICY_BLOCK = "POLICY_BLOCK"
REASON_POLICY_REVIEW_REQUIRED = "POLICY_REVIEW_REQUIRED"
REASON_POLICY_EXPIRED = "POLICY_EXPIRED"
REASON_POLICY_UNKNOWN = "POLICY_UNKNOWN"
REASON_POLICY_NOT_EFFECTIVE = "POLICY_NOT_EFFECTIVE"
REASON_INTEGRATION_UNAVAILABLE = "INTEGRATION_UNAVAILABLE"


class AutomationMode(StrEnum):
    """Independent level of automation (AUT-127, ``docs/03_DOMAIN_MODEL.md``)."""

    MANUAL = "MANUAL"
    SHADOW = "SHADOW"
    ASSISTED = "ASSISTED"
    AUTO = "AUTO"


class GlobalMode(StrEnum):
    """Global state of the Radar Core (AUT-149, AUT-228)."""

    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DRAINING = "DRAINING"
    MAINTENANCE = "MAINTENANCE"


class ExternalAction(StrEnum):
    """A request against the outside world, classified for authorization.

    ``PUBLISH``, ``BROWSER`` and ``AUTHENTICATED_LINK`` are side effects subject
    to mode/compliance/kill switch. ``READ``, ``DIAGNOSTIC`` and ``RECOVERY``
    remain available even under ``STOP_EXTERNAL_ACTIONS`` (AUT-317).
    """

    PUBLISH = "PUBLISH"
    BROWSER = "BROWSER"
    AUTHENTICATED_LINK = "AUTHENTICATED_LINK"
    READ = "READ"
    DIAGNOSTIC = "DIAGNOSTIC"
    RECOVERY = "RECOVERY"


class ComplianceStatus(StrEnum):
    """Status of a channel compliance policy (``docs/12_SECURITY_AND_COMPLIANCE.md``)."""

    ACTIVE = "ACTIVE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class IntegrationState(StrEnum):
    """Standardized external integration states (SDD-08 ``Estados externos``)."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


#: External actions that require authorization (side effects).
EXTERNAL_ACTIONS: frozenset[ExternalAction] = frozenset(
    {ExternalAction.PUBLISH, ExternalAction.BROWSER, ExternalAction.AUTHENTICATED_LINK}
)

#: Actions that must keep working under any operator command (AUT-317).
SAFE_ACTIONS: frozenset[ExternalAction] = frozenset(
    {ExternalAction.READ, ExternalAction.DIAGNOSTIC, ExternalAction.RECOVERY}
)

#: Integration states that allow the dependent capability to run.
OPERATIONAL_INTEGRATION_STATES: frozenset[IntegrationState] = frozenset(
    {IntegrationState.ONLINE, IntegrationState.DEGRADED}
)

#: Approved default when no automation policy rule matches: SHADOW never sends
#: commercially (AUT-011, AUT-368).
APPROVED_DEFAULT_AUTOMATION_MODE = AutomationMode.SHADOW

#: Maximum length of the free-form reason/summary fields.
MAX_OPERATIONS_TEXT_LENGTH = 512


class OperationsError(RadarException):
    """Base error raised when an operational control cannot be completed."""


def operations_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> OperationsError:
    """Build the structured ``RAD-WF-018`` error for invalid operations input."""

    return OperationsError(
        RadarError(
            code=OPERATIONS_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o input de operações e enviar novamente",
            context=dict(context or {}),
        )
    )


def automation_policy_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> OperationsError:
    """Build the structured ``RAD-CFG-012`` error for an invalid automation policy."""

    return OperationsError(
        RadarError(
            code=AUTOMATION_POLICY_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de automation policy e validar novamente",
            context=dict(context or {}),
        )
    )


def compliance_policy_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> OperationsError:
    """Build the structured ``RAD-CFG-013`` error for an invalid compliance policy."""

    return OperationsError(
        RadarError(
            code=COMPLIANCE_POLICY_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de compliance policy e validar novamente",
            context=dict(context or {}),
        )
    )


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _content_hash(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AutomationPolicyRule:
    """One rule that resolves an :class:`AutomationMode` for a context slice.

    The most specific matching rule wins; a rule with no matcher is rejected
    because it would silently override the default.
    """

    mode: AutomationMode
    brand: Brand | None = None
    marketplace: str | None = None
    channel: str | None = None
    capability: str | None = None

    @property
    def specificity(self) -> int:
        return sum(
            matcher is not None
            for matcher in (self.brand, self.marketplace, self.channel, self.capability)
        )

    def matches(
        self,
        *,
        brand: Brand | None,
        marketplace: str | None,
        channel: str | None,
        capability: str | None,
    ) -> bool:
        if self.brand is not None and self.brand is not brand:
            return False
        if self.marketplace is not None and self.marketplace != marketplace:
            return False
        if self.channel is not None and self.channel != channel:
            return False
        return self.capability is None or self.capability == capability


@dataclass(frozen=True, slots=True)
class AutomationPolicy:
    """Versioned, hashed autonomy policy (AUT-045, AUT-128, AUT-207)."""

    policy_version: str
    content_hash: str
    default_mode: AutomationMode = APPROVED_DEFAULT_AUTOMATION_MODE
    rules: tuple[AutomationPolicyRule, ...] = ()

    def mode_for(
        self,
        *,
        brand: Brand | None = None,
        marketplace: str | None = None,
        channel: str | None = None,
        capability: str | None = None,
    ) -> AutomationMode:
        """Resolve the mode for one brand/marketplace/channel/capability slice."""

        best: AutomationPolicyRule | None = None
        for rule in self.rules:
            if not rule.matches(
                brand=brand, marketplace=marketplace, channel=channel, capability=capability
            ):
                continue
            if best is None or rule.specificity > best.specificity:
                best = rule
        return self.default_mode if best is None else best.mode

    def to_contract(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_hash": self.content_hash,
            "default_mode": self.default_mode.value,
            "rules": [
                {
                    "mode": rule.mode.value,
                    "brand": None if rule.brand is None else rule.brand.value,
                    "marketplace": rule.marketplace,
                    "channel": rule.channel,
                    "capability": rule.capability,
                }
                for rule in self.rules
            ],
        }


def _coerce_brand(value: object, *, field_name: str) -> Brand | None:
    if value is None:
        return None
    try:
        return Brand(str(value))
    except ValueError as exc:
        raise automation_policy_invalid_error(
            "brand inválida na automation policy",
            context={"field": field_name, "value": str(value)},
        ) from exc


def build_automation_policy(document: Mapping[str, Any]) -> AutomationPolicy:
    """Build and validate the automation policy from a plain document.

    An unknown ``schema_version``, a missing version, an invalid mode/brand or a
    matcher-less rule fails closed with ``RAD-CFG-012``. A document without a
    ``default_mode`` keeps the approved SHADOW baseline.
    """

    if not isinstance(document, Mapping):
        raise automation_policy_invalid_error("Policy deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != AUTOMATION_POLICY_SCHEMA_VERSION:
        raise automation_policy_invalid_error(
            "schema_version de automation policy não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("policy_version") or "").strip()
    if not version:
        raise automation_policy_invalid_error("policy_version é obrigatório")

    default_mode = APPROVED_DEFAULT_AUTOMATION_MODE
    if document.get("default_mode") is not None:
        try:
            default_mode = AutomationMode(str(document["default_mode"]))
        except ValueError as exc:
            raise automation_policy_invalid_error(
                "default_mode inválido",
                context={"field": "default_mode"},
            ) from exc

    raw_rules = document.get("rules") or ()
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes)):
        raise automation_policy_invalid_error("rules deve ser uma lista")

    rules: list[AutomationPolicyRule] = []
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, Mapping):
            raise automation_policy_invalid_error(
                "cada rule deve ser um objeto", context={"index": index}
            )
        try:
            mode = AutomationMode(str(raw_rule.get("mode")))
        except ValueError as exc:
            raise automation_policy_invalid_error(
                "mode inválido em rule", context={"index": index}
            ) from exc
        brand = _coerce_brand(raw_rule.get("brand"), field_name="brand")
        marketplace = _optional_rule_text(raw_rule.get("marketplace"), field_name="marketplace")
        channel = _optional_rule_text(raw_rule.get("channel"), field_name="channel")
        capability = _optional_rule_text(raw_rule.get("capability"), field_name="capability")
        rule = AutomationPolicyRule(
            mode=mode,
            brand=brand,
            marketplace=marketplace,
            channel=channel,
            capability=capability,
        )
        if rule.specificity == 0:
            raise automation_policy_invalid_error(
                "rule precisa de ao menos um matcher", context={"index": index}
            )
        rules.append(rule)

    normalized = {
        "schema_version": AUTOMATION_POLICY_SCHEMA_VERSION,
        "policy_version": version,
        "default_mode": default_mode.value,
        "rules": [
            {
                "mode": rule.mode.value,
                "brand": None if rule.brand is None else rule.brand.value,
                "marketplace": rule.marketplace,
                "channel": rule.channel,
                "capability": rule.capability,
            }
            for rule in rules
        ],
    }
    return AutomationPolicy(
        policy_version=version,
        content_hash=_content_hash(normalized),
        default_mode=default_mode,
        rules=tuple(rules),
    )


def _optional_rule_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise automation_policy_invalid_error(
            "matcher deve ser texto não vazio", context={"field": field_name}
        )
    return value.strip()


#: Approved baseline: no rule invents autonomy; the default is SHADOW.
APPROVED_AUTOMATION_POLICY_DOCUMENT: dict[str, Any] = {
    "schema_version": AUTOMATION_POLICY_SCHEMA_VERSION,
    "policy_version": "automation-policy-1.0",
    "default_mode": APPROVED_DEFAULT_AUTOMATION_MODE.value,
}

#: The approved baseline automation policy.
APPROVED_AUTOMATION_POLICY = build_automation_policy(APPROVED_AUTOMATION_POLICY_DOCUMENT)


@dataclass(frozen=True, slots=True)
class ChannelCompliancePolicy:
    """Versioned, blocking compliance policy (AUT-293, AUT-294, AUT-295)."""

    policy_version: str
    content_hash: str
    status: ComplianceStatus = ComplianceStatus.UNKNOWN
    effective_from: datetime | None = None
    last_reviewed_at: datetime | None = None
    review_due_at: datetime | None = None
    source_reference: str | None = None

    def blocking_reason(self, now: datetime) -> str | None:
        """Return the block reason at ``now`` or ``None`` when the policy allows.

        Fail closed: an ``UNKNOWN``, ``REVIEW_REQUIRED`` or ``BLOCKED`` status, a
        policy whose review is due, or a policy not yet effective never releases
        an external side effect (AUT-295).
        """

        if self.status is ComplianceStatus.BLOCKED:
            return REASON_POLICY_BLOCK
        if self.status is ComplianceStatus.UNKNOWN:
            return REASON_POLICY_UNKNOWN
        if self.status is ComplianceStatus.REVIEW_REQUIRED:
            return REASON_POLICY_REVIEW_REQUIRED
        if self.review_due_at is not None and _to_utc(now) > _to_utc(self.review_due_at):
            return REASON_POLICY_EXPIRED
        if self.effective_from is not None and _to_utc(now) < _to_utc(self.effective_from):
            return REASON_POLICY_NOT_EFFECTIVE
        return None

    def to_contract(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_hash": self.content_hash,
            "status": self.status.value,
            "effective_from": (
                None if self.effective_from is None else _to_utc(self.effective_from).isoformat()
            ),
            "last_reviewed_at": (
                None
                if self.last_reviewed_at is None
                else _to_utc(self.last_reviewed_at).isoformat()
            ),
            "review_due_at": (
                None if self.review_due_at is None else _to_utc(self.review_due_at).isoformat()
            ),
            "source_reference": self.source_reference,
        }


def build_compliance_policy(document: Mapping[str, Any]) -> ChannelCompliancePolicy:
    """Build and validate the channel compliance policy from a plain document.

    A missing policy defaults to ``UNKNOWN`` (blocking). Invalid timestamps or an
    unknown status fail closed with ``RAD-CFG-013``.
    """

    if not isinstance(document, Mapping):
        raise compliance_policy_invalid_error("Policy deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != COMPLIANCE_POLICY_SCHEMA_VERSION:
        raise compliance_policy_invalid_error(
            "schema_version de compliance policy não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("policy_version") or "").strip()
    if not version:
        raise compliance_policy_invalid_error("policy_version é obrigatório")

    status = ComplianceStatus.UNKNOWN
    if document.get("status") is not None:
        try:
            status = ComplianceStatus(str(document["status"]))
        except ValueError as exc:
            raise compliance_policy_invalid_error(
                "status inválido",
                context={"field": "status"},
            ) from exc

    effective_from = _parse_compliance_datetime(document.get("effective_from"), "effective_from")
    last_reviewed_at = _parse_compliance_datetime(
        document.get("last_reviewed_at"), "last_reviewed_at"
    )
    review_due_at = _parse_compliance_datetime(document.get("review_due_at"), "review_due_at")
    source_reference = document.get("source_reference")
    if source_reference is not None:
        if not isinstance(source_reference, str) or not source_reference.strip():
            raise compliance_policy_invalid_error(
                "source_reference deve ser texto não vazio", context={"field": "source_reference"}
            )
        source_reference = source_reference.strip()

    normalized = {
        "schema_version": COMPLIANCE_POLICY_SCHEMA_VERSION,
        "policy_version": version,
        "status": status.value,
        "effective_from": None if effective_from is None else effective_from.isoformat(),
        "last_reviewed_at": None if last_reviewed_at is None else last_reviewed_at.isoformat(),
        "review_due_at": None if review_due_at is None else review_due_at.isoformat(),
        "source_reference": source_reference,
    }
    return ChannelCompliancePolicy(
        policy_version=version,
        content_hash=_content_hash(normalized),
        status=status,
        effective_from=effective_from,
        last_reviewed_at=last_reviewed_at,
        review_due_at=review_due_at,
        source_reference=source_reference,
    )


def _parse_compliance_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise compliance_policy_invalid_error(
            "timestamp deve ser texto ISO-8601", context={"field": field_name}
        )
    try:
        return _to_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError as exc:
        raise compliance_policy_invalid_error(
            "timestamp inválido", context={"field": field_name}
        ) from exc


#: Approved baseline: no compliance policy has been reviewed, so it is UNKNOWN
#: and blocks external side effects (AUT-295, fail closed).
APPROVED_COMPLIANCE_POLICY_DOCUMENT: dict[str, Any] = {
    "schema_version": COMPLIANCE_POLICY_SCHEMA_VERSION,
    "policy_version": "compliance-policy-1.0",
    "status": ComplianceStatus.UNKNOWN.value,
}

#: The approved baseline compliance policy.
APPROVED_COMPLIANCE_POLICY = build_compliance_policy(APPROVED_COMPLIANCE_POLICY_DOCUMENT)


@dataclass(frozen=True, slots=True)
class IntegrationHealth:
    """Standardized health of one external integration (AUT-139, AUT-243)."""

    name: str
    state: IntegrationState
    summary: str
    updated_at: datetime | None = None

    @property
    def is_operational(self) -> bool:
        """True when the integration can run its dependent capability."""

        return self.state in OPERATIONAL_INTEGRATION_STATES

    def to_contract(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "operational": self.is_operational,
            "summary": self.summary,
            "updated_at": None if self.updated_at is None else _to_utc(self.updated_at).isoformat(),
        }


@dataclass(frozen=True, slots=True)
class OperationalState:
    """Global operational state of the node (RDR-043, AUT-149, AUT-317)."""

    global_mode: GlobalMode = GlobalMode.RUNNING
    stop_external_actions: bool = False
    reason: str | None = None
    updated_at: datetime | None = None

    @property
    def blocks_new_external_actions(self) -> bool:
        """True when the state refuses *new* external side effects."""

        return self.stop_external_actions or self.global_mode is not GlobalMode.RUNNING

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": OPERATIONS_SCHEMA_VERSION,
            "global_mode": self.global_mode.value,
            "stop_external_actions": self.stop_external_actions,
            "blocks_new_external_actions": self.blocks_new_external_actions,
            "reason": self.reason,
            "updated_at": None if self.updated_at is None else _to_utc(self.updated_at).isoformat(),
        }


#: Approved initial state: RUNNING with the kill switch released (AUT-011).
DEFAULT_OPERATIONAL_STATE = OperationalState()


@dataclass(frozen=True, slots=True)
class ExternalActionRequest:
    """A classified request to authorize against the operational controls."""

    action: ExternalAction
    brand: Brand | None = None
    marketplace: str | None = None
    channel: str | None = None
    capability: str | None = None
    integration: str | None = None
    publication_approved: bool = False


@dataclass(frozen=True, slots=True)
class ExternalActionDecision:
    """Observable result of the authorization gate (RDR-043, GRILL-001)."""

    allowed: bool
    action: ExternalAction
    reason_code: str
    message: str
    automation_mode: AutomationMode
    compliance_status: ComplianceStatus
    global_mode: GlobalMode
    stop_external_actions: bool
    automation_policy_version: str
    compliance_policy_version: str
    correlation_id: str
    decided_at: datetime
    integration: str | None = None
    integration_state: IntegrationState | None = None
    external: bool = True

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": OPERATIONS_SCHEMA_VERSION,
            "allowed": self.allowed,
            "action": self.action.value,
            "external": self.external,
            "reason_code": self.reason_code,
            "message": self.message,
            "automation_mode": self.automation_mode.value,
            "compliance_status": self.compliance_status.value,
            "global_mode": self.global_mode.value,
            "stop_external_actions": self.stop_external_actions,
            "automation_policy_version": self.automation_policy_version,
            "compliance_policy_version": self.compliance_policy_version,
            "integration": self.integration,
            "integration_state": (
                None if self.integration_state is None else self.integration_state.value
            ),
            "correlation_id": self.correlation_id,
            "decided_at": _to_utc(self.decided_at).isoformat(),
        }


#: Deterministic, actionable operator message per reason code.
_REASON_MESSAGES: dict[str, str] = {
    REASON_ALLOWED: "Ação permitida pelas políticas operacionais vigentes",
    REASON_MANUAL_MODE: "Modo MANUAL não automatiza side effects externos",
    REASON_SHADOW_NO_COMMERCIAL_SEND: "SHADOW registra avaliações/previews, sem envio comercial",
    REASON_PUBLICATION_APPROVAL_REQUIRED: (
        "ASSISTED exige aprovação humana explícita da publicação; "
        "aprovação de Candidate não autoriza envio"
    ),
    REASON_STOP_EXTERNAL_ACTIONS: (
        "STOP_EXTERNAL_ACTIONS ativo: envio, browser e link autenticado bloqueados"
    ),
    REASON_GLOBAL_MODE_PAUSED: "Core em PAUSED: nenhum novo side effect externo é criado",
    REASON_GLOBAL_MODE_DRAINING: (
        "Core em DRAINING: apenas trabalho seguro já iniciado; novos side effects bloqueados"
    ),
    REASON_GLOBAL_MODE_MAINTENANCE: (
        "Core em MAINTENANCE: efeitos externos suspensos, diagnóstico disponível"
    ),
    REASON_POLICY_BLOCK: "Policy de compliance bloqueia explicitamente o side effect",
    REASON_POLICY_REVIEW_REQUIRED: "Policy de compliance exige revisão humana antes do side effect",
    REASON_POLICY_EXPIRED: "Policy de compliance vencida; revisar antes de liberar o side effect",
    REASON_POLICY_UNKNOWN: "Policy de compliance UNKNOWN não libera side effect por aprovação humana",
    REASON_POLICY_NOT_EFFECTIVE: "Policy de compliance ainda não vigente",
    REASON_INTEGRATION_UNAVAILABLE: (
        "Integração não operacional; a capability afetada fica isolada até recuperar saúde"
    ),
}


def _message_for(reason_code: str) -> str:
    return _REASON_MESSAGES.get(reason_code, "Ação bloqueada pelas políticas operacionais vigentes")


def decide_external_action(
    *,
    request: ExternalActionRequest,
    operational_state: OperationalState,
    automation_policy: AutomationPolicy,
    compliance_policy: ChannelCompliancePolicy,
    integration_health: IntegrationHealth | None = None,
    now: datetime,
    correlation_id: str,
) -> ExternalActionDecision:
    """Authorize or block one action (AUT-127, AUT-293, AUT-317, GRILL-001).

    Safe actions (reading, diagnostics, recovery) stay allowed under any operator
    command. An external side effect is blocked, in order, by the kill switch, the
    global mode, the compliance policy, the integration health and the automation
    mode. The mode is resolved for the requested brand/marketplace/channel/
    capability slice, so one unhealthy integration or one SHADOW slice never
    grants a commercial send.
    """

    automation_mode = automation_policy.mode_for(
        brand=request.brand,
        marketplace=request.marketplace,
        channel=request.channel,
        capability=request.capability,
    )

    def build(allowed: bool, reason_code: str) -> ExternalActionDecision:
        return ExternalActionDecision(
            allowed=allowed,
            action=request.action,
            reason_code=reason_code,
            message=_message_for(reason_code),
            automation_mode=automation_mode,
            compliance_status=compliance_policy.status,
            global_mode=operational_state.global_mode,
            stop_external_actions=operational_state.stop_external_actions,
            automation_policy_version=automation_policy.policy_version,
            compliance_policy_version=compliance_policy.policy_version,
            correlation_id=correlation_id,
            decided_at=_to_utc(now),
            integration=request.integration,
            integration_state=(None if integration_health is None else integration_health.state),
            external=request.action in EXTERNAL_ACTIONS,
        )

    if request.action not in EXTERNAL_ACTIONS:
        return build(True, REASON_ALLOWED)

    if operational_state.stop_external_actions:
        return build(False, REASON_STOP_EXTERNAL_ACTIONS)

    if operational_state.global_mode is GlobalMode.PAUSED:
        return build(False, REASON_GLOBAL_MODE_PAUSED)
    if operational_state.global_mode is GlobalMode.DRAINING:
        return build(False, REASON_GLOBAL_MODE_DRAINING)
    if operational_state.global_mode is GlobalMode.MAINTENANCE:
        return build(False, REASON_GLOBAL_MODE_MAINTENANCE)

    compliance_reason = compliance_policy.blocking_reason(now)
    if compliance_reason is not None:
        return build(False, compliance_reason)

    if request.integration is not None:
        unhealthy = integration_health is None or not integration_health.is_operational
        if unhealthy:
            return build(False, REASON_INTEGRATION_UNAVAILABLE)

    if automation_mode is AutomationMode.MANUAL:
        return build(False, REASON_MANUAL_MODE)
    if automation_mode is AutomationMode.SHADOW:
        return build(False, REASON_SHADOW_NO_COMMERCIAL_SEND)
    if automation_mode is AutomationMode.ASSISTED and not request.publication_approved:
        return build(False, REASON_PUBLICATION_APPROVAL_REQUIRED)
    return build(True, REASON_ALLOWED)


__all__ = [
    "APPROVED_AUTOMATION_POLICY",
    "APPROVED_AUTOMATION_POLICY_DOCUMENT",
    "APPROVED_COMPLIANCE_POLICY",
    "APPROVED_COMPLIANCE_POLICY_DOCUMENT",
    "APPROVED_DEFAULT_AUTOMATION_MODE",
    "AUTOMATION_POLICY_INVALID",
    "AUTOMATION_POLICY_SCHEMA_VERSION",
    "COMPLIANCE_POLICY_INVALID",
    "COMPLIANCE_POLICY_SCHEMA_VERSION",
    "DEFAULT_OPERATIONAL_STATE",
    "EXTERNAL_ACTIONS",
    "MAX_OPERATIONS_TEXT_LENGTH",
    "OPERATIONAL_INTEGRATION_STATES",
    "OPERATIONS_INPUT_INVALID",
    "OPERATIONS_SCHEMA_VERSION",
    "REASON_ALLOWED",
    "REASON_GLOBAL_MODE_DRAINING",
    "REASON_GLOBAL_MODE_MAINTENANCE",
    "REASON_GLOBAL_MODE_PAUSED",
    "REASON_INTEGRATION_UNAVAILABLE",
    "REASON_MANUAL_MODE",
    "REASON_POLICY_BLOCK",
    "REASON_POLICY_EXPIRED",
    "REASON_POLICY_NOT_EFFECTIVE",
    "REASON_POLICY_REVIEW_REQUIRED",
    "REASON_POLICY_UNKNOWN",
    "REASON_PUBLICATION_APPROVAL_REQUIRED",
    "REASON_SHADOW_NO_COMMERCIAL_SEND",
    "REASON_STOP_EXTERNAL_ACTIONS",
    "SAFE_ACTIONS",
    "AutomationMode",
    "AutomationPolicy",
    "AutomationPolicyRule",
    "ChannelCompliancePolicy",
    "ComplianceStatus",
    "ExternalAction",
    "ExternalActionDecision",
    "ExternalActionRequest",
    "GlobalMode",
    "IntegrationHealth",
    "IntegrationState",
    "OperationalState",
    "OperationsError",
    "automation_policy_invalid_error",
    "build_automation_policy",
    "build_compliance_policy",
    "compliance_policy_invalid_error",
    "decide_external_action",
    "operations_input_invalid_error",
]
