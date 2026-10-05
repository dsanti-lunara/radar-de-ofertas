"""SQLite engine factory (RDR-006).

SQLite is the canonical V1 store (AUT-199). Every connection enables WAL,
foreign keys and a busy timeout so durability and constraints are active from
the first query (AUT-200, AUT-233).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url

SQLITE_BUSY_TIMEOUT_MS = 5000


def _apply_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def create_database_engine(database_url: str) -> Engine:
    connect_args: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a threadpool; SQLite connections may be
        # reused across threads.
        connect_args["check_same_thread"] = False
    engine = create_engine(database_url, future=True, connect_args=connect_args)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


def ensure_sqlite_database_directory(database_url: str) -> None:
    """Create the parent directory of a file-backed SQLite database.

    Only bootstrap/upgrade commands may call this; read-only diagnostics must
    report an absent database instead of silently creating it.
    """

    if not database_url.startswith("sqlite"):
        return
    database = make_url(database_url).database
    if not database or database == ":memory:":
        return
    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)
