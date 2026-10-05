"""Secrets abstraction and least-privilege access (RDR-005, AUT-211, AUT-297).

Secrets never live in Git, YAML/config, the common database, logs, backups,
Knowledge Packs or prompts (AUT-210). A :class:`SecretsProvider` resolves a
logical reference to a :class:`Secret` at runtime; the provider only reads from
secure storage and never persists anything.

Every consumer receives a :class:`ScopedSecrets` bound to a :class:`SecretScope`
so a component can access *only* its own secrets; a missing secret blocks the
affected capability instead of silently degrading it (contract: "secret ausente
bloqueia capability afetada").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from radar.domain.config import SECRET_ACCESS_DENIED, SECRET_UNAVAILABLE
from radar.domain.errors import RadarError, RadarException

#: Value shown whenever a secret is rendered.
SECRET_MASK = "***REDACTED***"


@dataclass(frozen=True, slots=True)
class Secret:
    """An opaque secret value.

    ``repr``/``str`` are masked so a secret can never leak through accidental
    logging or exception formatting; callers must ask for :meth:`reveal`.
    """

    name: str
    _value: str = field(repr=False)

    def reveal(self) -> str:
        """Return the raw value; call this only at the point of use."""

        return self._value

    def __repr__(self) -> str:
        return f"Secret(name={self.name!r}, value={SECRET_MASK!r})"

    __str__ = __repr__


class SecretUnavailableError(RadarException):
    """Raised when a required secret is missing for a capability/component."""

    def __init__(self, name: str, component: str) -> None:
        super().__init__(
            RadarError(
                code=SECRET_UNAVAILABLE,
                message=f"Secret indisponível para a capability do componente '{component}'",
                retryable=False,
                action="Configurar o secret no armazenamento seguro do sistema e reiniciar",
                context={"secret": name, "component": component},
            )
        )


class SecretAccessDeniedError(RadarException):
    """Raised when a component requests a secret outside its least-privilege scope."""

    def __init__(self, name: str, component: str) -> None:
        super().__init__(
            RadarError(
                code=SECRET_ACCESS_DENIED,
                message=f"Componente '{component}' não tem permissão para este secret",
                retryable=False,
                action="Revisar a configuração de menor privilégio do componente",
                context={"secret": name, "component": component},
            )
        )


@runtime_checkable
class SecretsProvider(Protocol):
    """Read-only access to secrets in secure storage."""

    def get(self, name: str) -> Secret | None:
        """Return the secret for a logical reference, or ``None`` when absent."""
        ...


@dataclass(frozen=True, slots=True)
class SecretScope:
    """Least-privilege allow-list for one component (AUT-297)."""

    component: str
    allowed: frozenset[str]

    def permits(self, name: str) -> bool:
        return name in self.allowed


@dataclass(slots=True)
class ScopedSecrets:
    """A component's view over a :class:`SecretsProvider`.

    Access outside the scope fails closed even when the secret exists, and a
    missing secret raises :class:`SecretUnavailableError` so the affected
    capability is blocked rather than guessed.
    """

    provider: SecretsProvider
    scope: SecretScope

    def get(self, name: str) -> Secret | None:
        self._ensure_permitted(name)
        return self.provider.get(name)

    def require(self, name: str) -> Secret:
        secret = self.get(name)
        if secret is None:
            raise SecretUnavailableError(name, self.scope.component)
        return secret

    def _ensure_permitted(self, name: str) -> None:
        if not self.scope.permits(name):
            raise SecretAccessDeniedError(name, self.scope.component)
