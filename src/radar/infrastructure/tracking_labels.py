"""Tracking-label mapping loader with schema validation and hashing (RDR-070).

The external tracking-label mapping is versioned operational configuration kept
separate from code (AUT-045, AUT-205). Precedence is ``approved baseline < mapping
file``. The file is optional JSON at ``config/tracking-labels.json``; when present
it is validated and hashed by the domain builder. An explicitly configured file
that is missing or invalid fails closed with a structured ``RAD-CFG-015`` error
instead of silently falling back to the empty baseline (which assumes no label).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar.domain.errors import RadarError
from radar.domain.tracking import (
    APPROVED_TRACKING_LABEL_MAPPING,
    TRACKING_LABELS_INVALID,
    TrackingError,
    TrackingLabelMapping,
    build_tracking_label_mapping,
)

DEFAULT_TRACKING_LABELS_PATH = Path("config") / "tracking-labels.json"
ENV_TRACKING_LABELS_FILE = "RADAR_TRACKING_LABELS_FILE"


@dataclass(slots=True)
class TrackingLabelMappingLoader:
    """Load the effective versioned tracking-label mapping for one Radar node."""

    cwd: Path
    labels_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        labels_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> TrackingLabelMappingLoader:
        source = os.environ if env is None else env
        explicit = (
            labels_path if labels_path is not None else source.get(ENV_TRACKING_LABELS_FILE) or None
        )
        return cls(
            cwd=Path.cwd() if cwd is None else Path(cwd),
            labels_path=Path(explicit) if explicit else None,
        )

    def load(self) -> TrackingLabelMapping:
        path, required = self._resolve_path()
        if not path.exists():
            if required:
                raise TrackingError(
                    RadarError(
                        code=TRACKING_LABELS_INVALID,
                        message="Arquivo de mapeamento de etiquetas indicado não foi encontrado",
                        retryable=False,
                        action=(
                            "Criar o arquivo do mapeamento ou remover RADAR_TRACKING_LABELS_FILE"
                        ),
                        context={"path": str(path)},
                    )
                )
            return APPROVED_TRACKING_LABEL_MAPPING

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TrackingError(
                RadarError(
                    code=TRACKING_LABELS_INVALID,
                    message="Arquivo de mapeamento de etiquetas não pôde ser lido",
                    retryable=False,
                    action="Verificar permissões do arquivo do mapeamento de etiquetas",
                    context={"path": str(path), "reason": type(exc).__name__},
                )
            ) from exc

        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TrackingError(
                RadarError(
                    code=TRACKING_LABELS_INVALID,
                    message="Arquivo de mapeamento de etiquetas não é JSON válido",
                    retryable=False,
                    action="Corrigir o arquivo do mapeamento e validar novamente",
                    context={"path": str(path), "position": exc.pos},
                )
            ) from exc

        return build_tracking_label_mapping(data)

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.labels_path is not None:
            return self.labels_path, True
        return self.cwd / DEFAULT_TRACKING_LABELS_PATH, False


__all__ = [
    "DEFAULT_TRACKING_LABELS_PATH",
    "ENV_TRACKING_LABELS_FILE",
    "TrackingLabelMappingLoader",
]
