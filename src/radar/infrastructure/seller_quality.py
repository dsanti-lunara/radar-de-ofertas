"""Seller Quality normalization loader with schema validation and hashing (RDR-024).

Normalization of raw seller signals is operational configuration, not hardcoded
logic (AUT-045). Precedence is ``approved baseline < normalization file``. The
file is optional JSON at ``config/seller-quality.json``; when present it is
validated and hashed by the domain builder. An explicitly configured file that
is missing or invalid fails closed with a structured ``RAD-CFG-006`` error
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
from radar.domain.seller_quality import (
    APPROVED_SELLER_QUALITY_NORMALIZATION,
    SELLER_QUALITY_NORMALIZATION_INVALID,
    SellerQualityNormalization,
    SellerQualityNormalizationInvalidError,
    build_seller_quality_normalization,
)

DEFAULT_SELLER_QUALITY_PATH = Path("config") / "seller-quality.json"
ENV_SELLER_QUALITY_FILE = "RADAR_SELLER_QUALITY_FILE"


@dataclass(slots=True)
class SellerQualityLoader:
    """Load the effective versioned Seller Quality normalization for one node."""

    cwd: Path
    normalization_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        normalization_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> SellerQualityLoader:
        source = os.environ if env is None else env
        explicit = (
            normalization_path
            if normalization_path is not None
            else source.get(ENV_SELLER_QUALITY_FILE) or None
        )
        return cls(
            cwd=Path.cwd() if cwd is None else Path(cwd),
            normalization_path=Path(explicit) if explicit else None,
        )

    def load(self) -> SellerQualityNormalization:
        path, required = self._resolve_path()
        if not path.exists():
            if required:
                raise SellerQualityNormalizationInvalidError(
                    RadarError(
                        code=SELLER_QUALITY_NORMALIZATION_INVALID,
                        message="Arquivo de normalização de Seller Quality não foi encontrado",
                        retryable=False,
                        action=(
                            "Criar o arquivo de normalização ou remover RADAR_SELLER_QUALITY_FILE"
                        ),
                        context={"path": str(path)},
                    )
                )
            return APPROVED_SELLER_QUALITY_NORMALIZATION

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SellerQualityNormalizationInvalidError(
                RadarError(
                    code=SELLER_QUALITY_NORMALIZATION_INVALID,
                    message="Arquivo de normalização de Seller Quality não pôde ser lido",
                    retryable=False,
                    action="Verificar permissões do arquivo de normalização",
                    context={"path": str(path), "reason": type(exc).__name__},
                )
            ) from exc

        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SellerQualityNormalizationInvalidError(
                RadarError(
                    code=SELLER_QUALITY_NORMALIZATION_INVALID,
                    message="Arquivo de normalização de Seller Quality não é JSON válido",
                    retryable=False,
                    action="Corrigir o arquivo de normalização e validar novamente",
                    context={"path": str(path), "position": exc.pos},
                )
            ) from exc

        return build_seller_quality_normalization(data)

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.normalization_path is not None:
            return self.normalization_path, True
        return self.cwd / DEFAULT_SELLER_QUALITY_PATH, False


__all__ = [
    "DEFAULT_SELLER_QUALITY_PATH",
    "ENV_SELLER_QUALITY_FILE",
    "SellerQualityLoader",
]
