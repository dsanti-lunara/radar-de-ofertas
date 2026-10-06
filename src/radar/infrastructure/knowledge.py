"""Knowledge Pack loader with schema validation and hashing (RDR-045).

The Knowledge Pack is versioned editorial configuration, kept separate from the
operational config (AUT-205). Precedence is ``approved baseline < knowledge
file``. The file is optional JSON at ``config/knowledge-pack.json``; when present
it is validated and hashed by the domain builder. An explicitly configured file
that is missing or invalid fails closed with a structured ``RAD-CFG-014`` error
instead of silently falling back to the empty baseline.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar.domain.errors import RadarError
from radar.domain.knowledge import (
    APPROVED_KNOWLEDGE_PACK,
    KNOWLEDGE_INVALID,
    KnowledgeInvalidError,
    KnowledgePack,
    build_knowledge_pack,
)

DEFAULT_KNOWLEDGE_PATH = Path("config") / "knowledge-pack.json"
ENV_KNOWLEDGE_FILE = "RADAR_KNOWLEDGE_FILE"


@dataclass(slots=True)
class KnowledgePackLoader:
    """Load the effective versioned Knowledge Pack for one Radar node."""

    cwd: Path
    knowledge_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        knowledge_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> KnowledgePackLoader:
        source = os.environ if env is None else env
        explicit = (
            knowledge_path if knowledge_path is not None else source.get(ENV_KNOWLEDGE_FILE) or None
        )
        return cls(
            cwd=Path.cwd() if cwd is None else Path(cwd),
            knowledge_path=Path(explicit) if explicit else None,
        )

    def load(self) -> KnowledgePack:
        path, required = self._resolve_path()
        if not path.exists():
            if required:
                raise KnowledgeInvalidError(
                    RadarError(
                        code=KNOWLEDGE_INVALID,
                        message="Arquivo de Knowledge Pack indicado não foi encontrado",
                        retryable=False,
                        action="Criar o arquivo do Knowledge Pack ou remover RADAR_KNOWLEDGE_FILE",
                        context={"path": str(path)},
                    )
                )
            return APPROVED_KNOWLEDGE_PACK

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise KnowledgeInvalidError(
                RadarError(
                    code=KNOWLEDGE_INVALID,
                    message="Arquivo de Knowledge Pack não pôde ser lido",
                    retryable=False,
                    action="Verificar permissões do arquivo do Knowledge Pack",
                    context={"path": str(path), "reason": type(exc).__name__},
                )
            ) from exc

        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise KnowledgeInvalidError(
                RadarError(
                    code=KNOWLEDGE_INVALID,
                    message="Arquivo de Knowledge Pack não é JSON válido",
                    retryable=False,
                    action="Corrigir o arquivo do Knowledge Pack e validar novamente",
                    context={"path": str(path), "position": exc.pos},
                )
            ) from exc

        return build_knowledge_pack(data)

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.knowledge_path is not None:
            return self.knowledge_path, True
        return self.cwd / DEFAULT_KNOWLEDGE_PATH, False


__all__ = [
    "DEFAULT_KNOWLEDGE_PATH",
    "ENV_KNOWLEDGE_FILE",
    "KnowledgePackLoader",
]
