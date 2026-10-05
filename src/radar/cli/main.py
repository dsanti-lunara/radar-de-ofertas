"""``radarctl`` command-line skeleton (RDR-009).

Commands implemented at the foundation stage:

``radarctl status``   query system health (exit 0 only when operational)
``radarctl migrate``  apply migrations up to ``head``
``radarctl version``  print tool/app versions

``doctor`` (RDR-116) and the operational controls arrive in their own tickets.
Every command prints a versioned JSON contract including a correlation ID.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Sequence
from typing import Any

from radar import __version__
from radar.application.correlation import new_correlation_id
from radar.bootstrap import build_health_service
from radar.domain.errors import RadarError
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.migrations import upgrade_to_head
from radar.infrastructure.probes import MIGRATION_FAILED
from radar.infrastructure.settings import Settings

CLI_SCHEMA_VERSION = "1.0"


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_version(settings: Settings) -> int:
    _emit(
        {
            "schema_version": CLI_SCHEMA_VERSION,
            "app_version": settings.app_version,
            "radar_version": __version__,
            "python_version": platform.python_version(),
            "correlation_id": new_correlation_id(),
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
    correlation_id = new_correlation_id()
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radarctl", description="Operação local do Radar Engine.")
    parser.add_argument("--version", action="store_true", help="atalho para o comando version")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="consulta a saúde local")
    subparsers.add_parser("migrate", help="aplica migrations até head")
    subparsers.add_parser("version", help="mostra versões")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env()

    command = args.command
    if args.version and command is None:
        command = "version"

    if command == "version":
        return cmd_version(settings)
    if command == "status":
        return cmd_status(settings)
    if command == "migrate":
        return cmd_migrate(settings)

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
