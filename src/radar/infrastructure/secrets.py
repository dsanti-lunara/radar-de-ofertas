"""Environment-backed :class:`~radar.domain.secrets.SecretsProvider` (RDR-005).

Secrets are read from the process environment (a secure, non-persistent store)
and are never written back to config, the database, logs or fixtures. Only the
reference names come from configuration; values stay in the environment.

For a logical reference ``telegram_bot_token`` the default variable is
``RADAR_SECRET_TELEGRAM_BOT_TOKEN``; configuration may override the variable
name explicitly through ``secret_refs``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from radar.domain.secrets import Secret
from radar.infrastructure.logging import SecretRedactor

ENV_PREFIX = "RADAR_SECRET_"


def environment_variable_for(name: str) -> str:
    """Map a logical secret reference to its default environment variable."""

    normalized = name.strip().upper().replace("-", "_").replace(".", "_")
    return f"{ENV_PREFIX}{normalized}"


@dataclass(slots=True)
class EnvironmentSecretsProvider:
    """Resolve secrets from an environment mapping without persisting them."""

    env: Mapping[str, str]
    redactor: SecretRedactor | None = None
    references: Mapping[str, str] = field(default_factory=dict)

    def variable_name(self, name: str) -> str:
        return self.references.get(name) or environment_variable_for(name)

    def get(self, name: str) -> Secret | None:
        raw = self.env.get(self.variable_name(name))
        if not raw:
            return None
        if self.redactor is not None:
            # Defense in depth: any value that leaves the provider is masked in
            # logs even if a caller logs it by mistake.
            self.redactor.register(raw)
        return Secret(name=name, _value=raw)
