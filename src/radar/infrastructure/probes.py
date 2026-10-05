"""Health probes backed by real infrastructure (RDR-010).

The probes translate low-level failures into the structured error contract so
the operator can act without reading stack traces.
"""

from __future__ import annotations

from contextlib import suppress

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from radar.domain.errors import RadarError
from radar.domain.health import HealthCheck, HealthState
from radar.infrastructure.migrations import current_revision, head_revision

DATABASE_UNAVAILABLE = "RAD-DB-003"
DATABASE_INTEGRITY_FAILURE = "RAD-DB-001"
MIGRATION_FAILED = "RAD-DB-002"


class DatabaseHealthProbe:
    """Verify the database is reachable and configured for durability."""

    name = "database"

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def check(self) -> HealthCheck:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
                foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
        except OperationalError as exc:
            return HealthCheck(
                name=self.name,
                state=HealthState.UNHEALTHY,
                summary="Banco indisponível",
                error=RadarError(
                    code=DATABASE_UNAVAILABLE,
                    message=str(exc.orig or exc),
                    retryable=True,
                    action="Verificar caminho/permissão do banco e reiniciar o Radar",
                    context={"engine": self._engine.name},
                ),
            )
        except SQLAlchemyError as exc:
            return HealthCheck(
                name=self.name,
                state=HealthState.UNHEALTHY,
                summary="Falha de integridade do banco",
                error=RadarError(
                    code=DATABASE_INTEGRITY_FAILURE,
                    message=str(exc),
                    retryable=False,
                    action="Executar diagnóstico/restore conforme RECOVERY_RUNBOOK.md",
                    context={"engine": self._engine.name},
                ),
            )

        normalized_mode = "" if journal_mode is None else str(journal_mode).lower()
        foreign_keys_on = False
        with suppress(TypeError, ValueError):
            foreign_keys_on = int(foreign_keys or 0) == 1
        if normalized_mode != "wal" or not foreign_keys_on:
            return HealthCheck(
                name=self.name,
                state=HealthState.UNHEALTHY,
                summary="Banco sem WAL/foreign_keys ativos",
                error=RadarError(
                    code=DATABASE_INTEGRITY_FAILURE,
                    message=f"journal_mode={normalized_mode!r} foreign_keys={foreign_keys!r}",
                    retryable=False,
                    action="Verificar a configuração do SQLite antes de retomar o Radar",
                    context={"engine": self._engine.name},
                ),
            )
        return HealthCheck(
            name=self.name,
            state=HealthState.HEALTHY,
            summary="SQLite acessível com WAL e foreign keys ativos",
        )


class SchemaHealthProbe:
    """Verify the database schema is at the latest Alembic revision."""

    name = "schema"

    def __init__(self, engine: Engine, database_url: str) -> None:
        self._engine = engine
        self._database_url = database_url

    def check(self) -> HealthCheck:
        try:
            actual = current_revision(self._engine)
            expected = head_revision(self._database_url)
        except SQLAlchemyError as exc:
            return HealthCheck(
                name=self.name,
                state=HealthState.UNHEALTHY,
                summary="Falha ao ler o schema do banco",
                error=RadarError(
                    code=DATABASE_INTEGRITY_FAILURE,
                    message=str(exc),
                    retryable=False,
                    action="Executar diagnóstico/restore conforme RECOVERY_RUNBOOK.md",
                ),
            )
        except Exception as exc:  # migration wiring failures block side effects
            return HealthCheck(
                name=self.name,
                state=HealthState.UNHEALTHY,
                summary="Migrations indisponíveis",
                error=RadarError(
                    code=MIGRATION_FAILED,
                    message=str(exc),
                    retryable=False,
                    action="Verificar o diretório de migrations e executar radarctl migrate",
                ),
            )

        if actual != expected:
            return HealthCheck(
                name=self.name,
                state=HealthState.UNHEALTHY,
                summary="Schema fora da revisão mais recente",
                error=RadarError(
                    code=MIGRATION_FAILED,
                    message=f"revisão atual={actual!r} esperada={expected!r}",
                    retryable=False,
                    action="Executar radarctl migrate antes de iniciar os workers",
                    context={"current": actual or "", "head": expected or ""},
                ),
            )
        return HealthCheck(
            name=self.name,
            state=HealthState.HEALTHY,
            summary=f"Schema na revisão {actual}",
        )
