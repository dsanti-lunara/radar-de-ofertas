"""Configuration loader with schema validation and hashing (RDR-004).

Precedence is ``defaults < config file < environment``. The file is JSON so the
loader stays dependency-free; secrets are referenced by name only. Invalid
configuration raises :class:`~radar.domain.config.ConfigInvalidError` with an
actionable :class:`~radar.domain.errors.RadarError` instead of a stack trace.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.engine import make_url

from radar.domain.config import (
    CONFIG_INVALID,
    CONFIG_SCHEMA_VERSION,
    CONFIG_UNREADABLE,
    VALID_AUTOMATION_MODES,
    VALID_LOG_LEVELS,
    ConfigInvalidError,
    RadarConfig,
)
from radar.domain.errors import RadarError

DEFAULT_CONFIG_PATH = Path("config") / "radar.json"
ENV_CONFIG_FILE = "RADAR_CONFIG_FILE"

_ENV_FIELD_MAP: dict[str, str] = {
    "RADAR_ENVIRONMENT": "environment",
    "RADAR_TIMEZONE": "timezone",
    "RADAR_LOG_LEVEL": "log_level",
    "RADAR_AUTOMATION_MODE": "automation_mode",
    "RADAR_DATA_DIR": "data_dir",
    "RADAR_DATABASE_URL": "database_url",
}

_ENVIRONMENT_PATTERN = re.compile(r"[a-z][a-z0-9_-]{1,31}")
_SECRET_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
_ENV_VAR_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    environment: str = "development"
    timezone: str = "America/Maceio"
    log_level: str = "INFO"
    automation_mode: str = "SHADOW"
    data_dir: str | None = None
    database_url: str | None = None
    secrets: dict[str, str] = Field(default_factory=dict)

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        if not _ENVIRONMENT_PATTERN.fullmatch(value):
            raise ValueError("ambiente deve ser minúsculo alfanumérico (ex.: development)")
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in VALID_LOG_LEVELS:
            raise ValueError(f"log_level inválido; use um de {sorted(VALID_LOG_LEVELS)}")
        return normalized

    @field_validator("automation_mode")
    @classmethod
    def _validate_automation_mode(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in VALID_AUTOMATION_MODES:
            raise ValueError(
                f"automation_mode inválido; use um de {sorted(VALID_AUTOMATION_MODES)}"
            )
        return normalized

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("timezone IANA inválido (ex.: America/Maceio)") from exc
        return value

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            make_url(value)
        except Exception as exc:
            raise ValueError("database_url inválida") from exc
        return value

    @field_validator("secrets")
    @classmethod
    def _validate_secrets(cls, value: dict[str, str]) -> dict[str, str]:
        for name, reference in value.items():
            if not _SECRET_NAME_PATTERN.fullmatch(name):
                raise ValueError(f"referência de secret inválida: {name!r}")
            if not _ENV_VAR_PATTERN.fullmatch(reference):
                raise ValueError(f"variável de ambiente inválida para o secret {name!r}")
        return value


@dataclass(slots=True)
class ConfigLoader:
    """Compose and validate the effective configuration for one node."""

    env: Mapping[str, str]
    cwd: Path
    config_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        config_path: Path | str | None = None,
        cwd: Path | str | None = None,
    ) -> ConfigLoader:
        source = os.environ if env is None else env
        explicit = config_path if config_path is not None else source.get(ENV_CONFIG_FILE) or None
        return cls(
            env=source,
            cwd=Path.cwd() if cwd is None else Path(cwd),
            config_path=Path(explicit) if explicit else None,
        )

    def load(self) -> RadarConfig:
        path, required = self._resolve_path()
        file_values = self._read_file(path, required=required)

        effective: dict[str, Any] = dict(file_values)
        env_overrides: list[str] = []
        for env_key, field in _ENV_FIELD_MAP.items():
            value = self.env.get(env_key)
            if value:
                effective[field] = value
                env_overrides.append(env_key)

        model = self._validate(effective, path=path)
        data_dir = model.data_dir or str(self.cwd / "data")
        database_url = model.database_url or (
            f"sqlite+pysqlite:///{(Path(data_dir) / 'radar.db').as_posix()}"
        )
        secret_refs = dict(model.secrets)
        config_hash = _compute_hash(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "environment": model.environment,
                "timezone": model.timezone,
                "log_level": model.log_level,
                "automation_mode": model.automation_mode,
                "data_dir": data_dir,
                "database_url": database_url,
                "secret_refs": dict(sorted(secret_refs.items())),
            }
        )

        sources: list[str] = []
        if file_values:
            sources.append(str(path))
        if env_overrides:
            sources.append("env")
        return RadarConfig(
            environment=model.environment,
            timezone=model.timezone,
            log_level=model.log_level,
            automation_mode=model.automation_mode,
            data_dir=data_dir,
            database_url=database_url,
            config_hash=config_hash,
            source="+".join(sources) or "defaults",
            secret_refs=secret_refs,
        )

    def _resolve_path(self) -> tuple[Path, bool]:
        if self.config_path is not None:
            return self.config_path, True
        return self.cwd / DEFAULT_CONFIG_PATH, False

    def _read_file(self, path: Path, *, required: bool) -> dict[str, Any]:
        if not path.exists():
            if required:
                raise ConfigInvalidError(
                    RadarError(
                        code=CONFIG_UNREADABLE,
                        message="Arquivo de configuração indicado não foi encontrado",
                        retryable=False,
                        action="Criar o arquivo de config ou remover RADAR_CONFIG_FILE",
                        context={"path": str(path)},
                    )
                )
            return {}
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigInvalidError(
                RadarError(
                    code=CONFIG_UNREADABLE,
                    message="Arquivo de configuração não pôde ser lido",
                    retryable=False,
                    action="Verificar permissões do arquivo de config",
                    context={"path": str(path), "reason": type(exc).__name__},
                )
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigInvalidError(
                RadarError(
                    code=CONFIG_INVALID,
                    message="Arquivo de configuração não é JSON válido",
                    retryable=False,
                    action="Corrigir o arquivo de config e executar novamente",
                    context={"path": str(path), "position": exc.pos},
                )
            ) from exc
        if not isinstance(data, dict):
            raise ConfigInvalidError(
                RadarError(
                    code=CONFIG_INVALID,
                    message="Configuração deve ser um objeto JSON",
                    retryable=False,
                    action="Corrigir o arquivo de config e executar novamente",
                    context={"path": str(path)},
                )
            )
        return data

    def _validate(self, values: dict[str, Any], *, path: Path) -> _ConfigModel:
        try:
            return _ConfigModel.model_validate(values)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc']) or '(raiz)'}: {error['msg']}"
                for error in exc.errors(include_input=False)
            )
            raise ConfigInvalidError(
                RadarError(
                    code=CONFIG_INVALID,
                    message=f"Configuração inválida: {details}",
                    retryable=False,
                    action="Corrigir config/radar.json ou as variáveis RADAR_* e executar novamente",
                    context={"path": str(path)},
                )
            ) from exc


def _compute_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
