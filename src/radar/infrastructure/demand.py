"""Demand normalization loader with schema validation and hashing (RDR-025).

Normalization of raw demand signals is operational configuration, not hardcoded
logic (AUT-045, AUT-050). Precedence is ``approved baseline < normalization
file``. The file is optional JSON at ``config/demand.json``; when present it is
validated and hashed by the domain builder. An explicitly configured file that is
missing or invalid fails closed with a structured ``RAD-CFG-007`` error instead
of silently falling back to the empty baseline.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar.domain.demand import (
    APPROVED_DEMAND_NORMALIZATION,
    DEMAND_NORMALIZATION_INVALID,
    DemandNormalization,
    DemandNormalizationInvalidError,
    build_demand_normalization,
)
from radar.domain.errors import RadarError

DEFAULT_DEMAND_PATH = Path("config") / "demand.json"
ENV_DEMAND_FILE = "RADAR_DEMAND_FILE"


@dataclass(slots=True)
class DemandLoader:
    """Load the effective versioned Demand normalization for one node."""

    cwd: Path
    normalization_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        normalization_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> DemandLoader:
        source = os.environ if env is None else env
        explicit = (
            normalization_path
            if normalization_path is not None
            else source.get(ENV_DEMAND_FILE) or None
        )
        return cls(
            cwd=Path.cwd() if cwd is None else Path(cwd),
            normalization_path=Path(explicit) if explicit else None,
        )

    def load(self) -> DemandNormalization:
        path, required = self._resolve_path()
        if not path.exists():
            if required:
                raise DemandNormalizationInvalidError(
                    RadarError(
                        code=DEMAND_NORMALIZATION_INVALID,
                        message="Arquivo de normalização de Demand não foi encontrado",
                        retryable=False,
                        action="Criar o arquivo de normalização ou remover RADAR_DEMAND_FILE",
                        context={"path": str(path)},
                    )
                )
            return APPROVED_DEMAND_NORMALIZATION

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DemandNormalizationInvalidError(
                RadarError(
                    code=DEMAND_NORMALIZATION_INVALID,
                    message="Arquivo de normalização de Demand não pôde ser lido",
                    retryable=False,
                    action="Verificar permissões do arquivo de normalização",
                    context={"path": str(path), "reason": type(exc).__name__},
                )
            ) from exc

        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DemandNormalizationInvalidError(
                RadarError(
                    code=DEMAND_NORMALIZATION_INVALID,
                    message="Arquivo de normalização de Demand não é JSON válido",
                    retryable=False,
                    action="Corrigir o arquivo de normalização e validar novamente",
                    context={"path": str(path), "position": exc.pos},
                )
            ) from exc

        return build_demand_normalization(data)

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.normalization_path is not None:
            return self.normalization_path, True
        return self.cwd / DEFAULT_DEMAND_PATH, False


__all__ = [
    "DEFAULT_DEMAND_PATH",
    "ENV_DEMAND_FILE",
    "DemandLoader",
]
