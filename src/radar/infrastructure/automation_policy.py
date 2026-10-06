"""Automation policy loader with schema validation and hashing (RDR-043).

Autonomy is operational configuration, not hardcoded logic (AUT-045, AUT-128).
Precedence is ``approved baseline < policy file``. The file is optional JSON at
``config/automation-policy.json``; when present it is validated and hashed by the
domain builder. An explicitly configured file that is missing or invalid fails
closed with a structured ``RAD-CFG-012`` error instead of silently falling back to
the baseline.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar.domain.errors import RadarError
from radar.domain.operations import (
    APPROVED_AUTOMATION_POLICY,
    AUTOMATION_POLICY_INVALID,
    AutomationPolicy,
    OperationsError,
    build_automation_policy,
)

DEFAULT_AUTOMATION_POLICY_PATH = Path("config") / "automation-policy.json"
ENV_AUTOMATION_POLICY_FILE = "RADAR_AUTOMATION_POLICY_FILE"


@dataclass(slots=True)
class AutomationPolicyLoader:
    """Load the effective versioned automation policy for one node."""

    cwd: Path
    policy_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        policy_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> AutomationPolicyLoader:
        source = os.environ if env is None else env
        explicit = (
            policy_path
            if policy_path is not None
            else source.get(ENV_AUTOMATION_POLICY_FILE) or None
        )
        return cls(
            cwd=Path.cwd() if cwd is None else Path(cwd),
            policy_path=Path(explicit) if explicit else None,
        )

    def load(self) -> AutomationPolicy:
        path, required = self._resolve_path()
        if not path.exists():
            if required:
                raise OperationsError(
                    RadarError(
                        code=AUTOMATION_POLICY_INVALID,
                        message="Arquivo de automation policy não foi encontrado",
                        retryable=False,
                        action=(
                            "Criar o arquivo de policy ou remover RADAR_AUTOMATION_POLICY_FILE"
                        ),
                        context={"path": str(path)},
                    )
                )
            return APPROVED_AUTOMATION_POLICY

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OperationsError(
                RadarError(
                    code=AUTOMATION_POLICY_INVALID,
                    message="Arquivo de automation policy não pôde ser lido",
                    retryable=False,
                    action="Verificar permissões do arquivo de policy",
                    context={"path": str(path), "reason": type(exc).__name__},
                )
            ) from exc

        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OperationsError(
                RadarError(
                    code=AUTOMATION_POLICY_INVALID,
                    message="Arquivo de automation policy não é JSON válido",
                    retryable=False,
                    action="Corrigir o arquivo de policy e validar novamente",
                    context={"path": str(path), "position": exc.pos},
                )
            ) from exc

        return build_automation_policy(data)

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.policy_path is not None:
            return self.policy_path, True
        return self.cwd / DEFAULT_AUTOMATION_POLICY_PATH, False


__all__ = [
    "DEFAULT_AUTOMATION_POLICY_PATH",
    "ENV_AUTOMATION_POLICY_FILE",
    "AutomationPolicyLoader",
]
