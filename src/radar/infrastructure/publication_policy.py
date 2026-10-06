"""Publication policy loader with schema validation and hashing (RDR-020).

The hard cap, burst, cooldown and quiet hours are operational configuration, not
hardcoded logic (AUT-045, AUT-175). Precedence is ``approved baseline < policy
file``. The file is optional JSON at ``config/publication-policy.json``; when
present it is validated and hashed by the domain builder. An explicitly
configured file that is missing or invalid fails closed with a structured
``RAD-CFG-016`` error instead of silently falling back to the baseline.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar.domain.errors import RadarError
from radar.domain.publication import (
    APPROVED_PUBLICATION_POLICY,
    PUBLICATION_POLICY_INVALID,
    PublicationError,
    PublicationPolicy,
    build_publication_policy,
)

DEFAULT_PUBLICATION_POLICY_PATH = Path("config") / "publication-policy.json"
ENV_PUBLICATION_POLICY_FILE = "RADAR_PUBLICATION_POLICY_FILE"


def _invalid(message: str, *, context: Mapping[str, Any]) -> PublicationError:
    return PublicationError(
        RadarError(
            code=PUBLICATION_POLICY_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de publication policy e validar novamente",
            context=dict(context),
        )
    )


@dataclass(slots=True)
class PublicationPolicyLoader:
    """Load the effective versioned publication policy for one node."""

    cwd: Path
    policy_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        policy_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> PublicationPolicyLoader:
        source = os.environ if env is None else env
        explicit = (
            policy_path
            if policy_path is not None
            else source.get(ENV_PUBLICATION_POLICY_FILE) or None
        )
        return cls(
            cwd=Path.cwd() if cwd is None else Path(cwd),
            policy_path=Path(explicit) if explicit else None,
        )

    def load(self) -> PublicationPolicy:
        path, required = self._resolve_path()
        if not path.exists():
            if required:
                raise _invalid(
                    "Arquivo de publication policy não foi encontrado",
                    context={"path": str(path)},
                )
            return APPROVED_PUBLICATION_POLICY

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise _invalid(
                "Arquivo de publication policy não pôde ser lido",
                context={"path": str(path), "reason": type(exc).__name__},
            ) from exc

        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise _invalid(
                "Arquivo de publication policy não é JSON válido",
                context={"path": str(path), "position": exc.pos},
            ) from exc

        return build_publication_policy(data)

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.policy_path is not None:
            return self.policy_path, True
        return self.cwd / DEFAULT_PUBLICATION_POLICY_PATH, False


__all__ = [
    "DEFAULT_PUBLICATION_POLICY_PATH",
    "ENV_PUBLICATION_POLICY_FILE",
    "PublicationPolicyLoader",
]
