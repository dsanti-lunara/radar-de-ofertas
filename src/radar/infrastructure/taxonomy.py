"""Taxonomy loader with schema validation and hashing (RDR-022, RDR-026).

The brand taxonomy is operational configuration, not hardcoded logic (AUT-045).
Precedence is ``approved baseline < taxonomy file``. The file is optional JSON at
``config/brand-taxonomy.json``; when present it is validated and hashed by the
domain builder. An explicitly configured file that is missing or invalid fails
closed with a structured ``RAD-CFG-005`` error instead of silently falling back.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar.domain.errors import RadarError
from radar.domain.taxonomy import (
    APPROVED_TAXONOMY,
    TAXONOMY_INVALID,
    BrandTaxonomy,
    TaxonomyInvalidError,
    build_taxonomy,
)

DEFAULT_TAXONOMY_PATH = Path("config") / "brand-taxonomy.json"
ENV_TAXONOMY_FILE = "RADAR_TAXONOMY_FILE"


@dataclass(slots=True)
class TaxonomyLoader:
    """Load the effective versioned taxonomy for one Radar node."""

    cwd: Path
    taxonomy_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        taxonomy_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> TaxonomyLoader:
        source = os.environ if env is None else env
        explicit = (
            taxonomy_path if taxonomy_path is not None else source.get(ENV_TAXONOMY_FILE) or None
        )
        return cls(
            cwd=Path.cwd() if cwd is None else Path(cwd),
            taxonomy_path=Path(explicit) if explicit else None,
        )

    def load(self) -> BrandTaxonomy:
        path, required = self._resolve_path()
        if not path.exists():
            if required:
                raise TaxonomyInvalidError(
                    RadarError(
                        code=TAXONOMY_INVALID,
                        message="Arquivo de taxonomia indicado não foi encontrado",
                        retryable=False,
                        action="Criar o arquivo de taxonomia ou remover RADAR_TAXONOMY_FILE",
                        context={"path": str(path)},
                    )
                )
            return APPROVED_TAXONOMY

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TaxonomyInvalidError(
                RadarError(
                    code=TAXONOMY_INVALID,
                    message="Arquivo de taxonomia não pôde ser lido",
                    retryable=False,
                    action="Verificar permissões do arquivo de taxonomia",
                    context={"path": str(path), "reason": type(exc).__name__},
                )
            ) from exc

        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TaxonomyInvalidError(
                RadarError(
                    code=TAXONOMY_INVALID,
                    message="Arquivo de taxonomia não é JSON válido",
                    retryable=False,
                    action="Corrigir o arquivo de taxonomia e validar novamente",
                    context={"path": str(path), "position": exc.pos},
                )
            ) from exc

        return build_taxonomy(data)

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.taxonomy_path is not None:
            return self.taxonomy_path, True
        return self.cwd / DEFAULT_TAXONOMY_PATH, False


__all__ = [
    "DEFAULT_TAXONOMY_PATH",
    "ENV_TAXONOMY_FILE",
    "TaxonomyLoader",
]
