"""Retry policy loader with schema validation and hashing (RDR-037).

The transient backoff schedule is operational configuration, not hardcoded logic
(AUT-130). Precedence is ``approved baseline < policy file``. The file is optional
JSON at ``config/retry-policy.json``; when present it is validated and hashed by
the domain builder. An explicitly configured file that is missing or invalid
fails closed with a structured ``RAD-CFG-010`` error instead of silently falling
back to the baseline.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar.domain.errors import RadarError
from radar.domain.retry import (
    APPROVED_RETRY_POLICY,
    RETRY_POLICY_INVALID,
    RetryError,
    RetryPolicy,
    build_retry_policy,
)

DEFAULT_RETRY_PATH = Path("config") / "retry-policy.json"
ENV_RETRY_FILE = "RADAR_RETRY_FILE"


@dataclass(slots=True)
class RetryPolicyLoader:
    """Load the effective versioned retry policy for one node."""

    cwd: Path
    policy_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        policy_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> RetryPolicyLoader:
        source = os.environ if env is None else env
        explicit = policy_path if policy_path is not None else source.get(ENV_RETRY_FILE) or None
        return cls(
            cwd=Path.cwd() if cwd is None else Path(cwd),
            policy_path=Path(explicit) if explicit else None,
        )

    def load(self) -> RetryPolicy:
        path, required = self._resolve_path()
        if not path.exists():
            if required:
                raise RetryError(
                    RadarError(
                        code=RETRY_POLICY_INVALID,
                        message="Arquivo de policy de retry não foi encontrado",
                        retryable=False,
                        action="Criar o arquivo de policy ou remover RADAR_RETRY_FILE",
                        context={"path": str(path)},
                    )
                )
            return APPROVED_RETRY_POLICY

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RetryError(
                RadarError(
                    code=RETRY_POLICY_INVALID,
                    message="Arquivo de policy de retry não pôde ser lido",
                    retryable=False,
                    action="Verificar permissões do arquivo de policy",
                    context={"path": str(path), "reason": type(exc).__name__},
                )
            ) from exc

        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RetryError(
                RadarError(
                    code=RETRY_POLICY_INVALID,
                    message="Arquivo de policy de retry não é JSON válido",
                    retryable=False,
                    action="Corrigir o arquivo de policy e validar novamente",
                    context={"path": str(path), "position": exc.pos},
                )
            ) from exc

        return build_retry_policy(data)

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.policy_path is not None:
            return self.policy_path, True
        return self.cwd / DEFAULT_RETRY_PATH, False


__all__ = [
    "DEFAULT_RETRY_PATH",
    "ENV_RETRY_FILE",
    "RetryPolicyLoader",
]
