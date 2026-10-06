"""Workflow policy loader with schema validation and hashing (RDR-041).

The Candidate/Opportunity TTLs are operational configuration, not hardcoded logic
(AUT-045). Precedence is ``approved baseline < policy file``. The file is optional
JSON at ``config/opportunity-workflow.json``; when present it is validated and
hashed by the domain builder. An explicitly configured file that is missing or
invalid fails closed with a structured ``RAD-CFG-011`` error instead of silently
falling back to the baseline.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar.domain.errors import RadarError
from radar.domain.workflow import (
    APPROVED_WORKFLOW_POLICY,
    WORKFLOW_POLICY_INVALID,
    WorkflowError,
    WorkflowPolicy,
    build_workflow_policy,
)

DEFAULT_WORKFLOW_PATH = Path("config") / "opportunity-workflow.json"
ENV_WORKFLOW_FILE = "RADAR_WORKFLOW_FILE"


@dataclass(slots=True)
class WorkflowPolicyLoader:
    """Load the effective versioned workflow policy for one node."""

    cwd: Path
    policy_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        policy_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> WorkflowPolicyLoader:
        source = os.environ if env is None else env
        explicit = policy_path if policy_path is not None else source.get(ENV_WORKFLOW_FILE) or None
        return cls(
            cwd=Path.cwd() if cwd is None else Path(cwd),
            policy_path=Path(explicit) if explicit else None,
        )

    def load(self) -> WorkflowPolicy:
        path, required = self._resolve_path()
        if not path.exists():
            if required:
                raise WorkflowError(
                    RadarError(
                        code=WORKFLOW_POLICY_INVALID,
                        message="Arquivo de policy do workflow não foi encontrado",
                        retryable=False,
                        action="Criar o arquivo de policy ou remover RADAR_WORKFLOW_FILE",
                        context={"path": str(path)},
                    )
                )
            return APPROVED_WORKFLOW_POLICY

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkflowError(
                RadarError(
                    code=WORKFLOW_POLICY_INVALID,
                    message="Arquivo de policy do workflow não pôde ser lido",
                    retryable=False,
                    action="Verificar permissões do arquivo de policy",
                    context={"path": str(path), "reason": type(exc).__name__},
                )
            ) from exc

        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkflowError(
                RadarError(
                    code=WORKFLOW_POLICY_INVALID,
                    message="Arquivo de policy do workflow não é JSON válido",
                    retryable=False,
                    action="Corrigir o arquivo de policy e validar novamente",
                    context={"path": str(path), "position": exc.pos},
                )
            ) from exc

        return build_workflow_policy(data)

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.policy_path is not None:
            return self.policy_path, True
        return self.cwd / DEFAULT_WORKFLOW_PATH, False


__all__ = [
    "DEFAULT_WORKFLOW_PATH",
    "ENV_WORKFLOW_FILE",
    "WorkflowPolicyLoader",
]
