"""``radarctl`` command-line skeleton (RDR-009).

Commands implemented at the foundation stage:

``radarctl status``   query system health (exit 0 only when operational)
``radarctl migrate``  apply migrations up to ``head``
``radarctl version``  print tool/app versions
``radarctl config``   load, validate and display the sanitized configuration

``doctor`` (RDR-116) and the operational controls arrive in their own tickets.
Every command prints a versioned JSON contract including a correlation ID.
Invalid configuration blocks execution before any command runs (RDR-004).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from collections.abc import Sequence
from typing import Any

from radar import __version__
from radar.application.correlation import bind_correlation_id, current_correlation_id
from radar.bootstrap import build_health_service
from radar.domain.config import ConfigInvalidError, RadarConfig
from radar.domain.errors import RadarError
from radar.infrastructure.config import ConfigLoader
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.logging import SecretRedactor, configure_logging, get_logger
from radar.infrastructure.migrations import upgrade_to_head
from radar.infrastructure.probes import MIGRATION_FAILED
from radar.infrastructure.secrets import EnvironmentSecretsProvider
from radar.infrastructure.settings import Settings

CLI_SCHEMA_VERSION = "1.0"


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_version(settings: Settings, config: RadarConfig) -> int:
    _emit(
        {
            "schema_version": CLI_SCHEMA_VERSION,
            "app_version": settings.app_version,
            "radar_version": __version__,
            "python_version": platform.python_version(),
            "environment": config.environment,
            "config_hash": config.config_hash,
            "correlation_id": current_correlation_id(),
        }
    )
    return 0


def cmd_config(config: RadarConfig, redactor: SecretRedactor) -> int:
    provider = EnvironmentSecretsProvider(
        env=os.environ,
        redactor=redactor,
        references=config.secret_refs,
    )
    secret_status = {
        name: "present" if provider.get(name) is not None else "missing"
        for name in sorted(config.secret_refs)
    }
    _emit(
        {
            "schema_version": CLI_SCHEMA_VERSION,
            "status": "VALID",
            "correlation_id": current_correlation_id(),
            "config": config.to_contract(),
            "secrets": {
                "declared": sorted(config.secret_refs),
                "status": secret_status,
            },
        }
    )
    return 0


def cmd_status(settings: Settings) -> int:
    engine = create_database_engine(settings.database_url)
    try:
        report = build_health_service(settings, engine).evaluate()
    finally:
        engine.dispose()
    _emit(report.to_contract())
    return 0 if report.is_operational else 1


def cmd_migrate(settings: Settings) -> int:
    correlation_id = current_correlation_id()
    try:
        upgrade_to_head(settings.database_url)
    except Exception as exc:
        error = RadarError(
            code=MIGRATION_FAILED,
            message=str(exc),
            retryable=False,
            action="Corrigir a migration e executar radarctl migrate novamente",
        )
        _emit(
            {
                "schema_version": CLI_SCHEMA_VERSION,
                "status": "UNHEALTHY",
                "correlation_id": correlation_id,
                "error": error.to_contract(),
            }
        )
        return 1
    _emit(
        {
            "schema_version": CLI_SCHEMA_VERSION,
            "status": "HEALTHY",
            "correlation_id": correlation_id,
        }
    )
    return 0


def _emit_config_error(error: RadarError) -> None:
    _emit(
        {
            "schema_version": CLI_SCHEMA_VERSION,
            "status": "INVALID",
            "correlation_id": current_correlation_id(),
            "error": error.to_contract(),
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radarctl", description="Operação local do Radar Engine.")
    parser.add_argument("--version", action="store_true", help="atalho para o comando version")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="consulta a saúde local")
    subparsers.add_parser("migrate", help="aplica migrations até head")
    subparsers.add_parser("version", help="mostra versões")
    subparsers.add_parser("config", help="valida e exibe a configuração sanitizada")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    bind_correlation_id()

    redactor = SecretRedactor()
    try:
        config = ConfigLoader.from_env().load()
    except ConfigInvalidError as exc:
        configure_logging("INFO", redactor=redactor)
        get_logger("cli").error("configuração inválida", extra={"error_code": exc.error.code})
        _emit_config_error(exc.error)
        return 1

    configure_logging(config.log_level, redactor=redactor)
    get_logger("cli").info("configuração validada", extra={"config_hash": config.config_hash})

    settings = Settings(database_url=config.database_url, log_level=config.log_level)

    command = args.command
    if args.version and command is None:
        command = "version"

    if command == "version":
        return cmd_version(settings, config)
    if command == "status":
        return cmd_status(settings)
    if command == "migrate":
        return cmd_migrate(settings)
    if command == "config":
        return cmd_config(config, redactor)

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
