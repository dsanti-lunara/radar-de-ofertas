"""publication lifecycle and append-only events

Revision ID: 0017_publication
Revises: 0016_ai_input_cache
Create Date: 2026-10-06

Introduces the ``publication`` table (RDR-020, RDR-072) — the confirmed send of
one validated ContentGeneration, distinct from ContentGeneration/Opportunity
(AUT-025, AUT-034) — and the append-only ``publication_event`` history. The
``uq_publication_idempotency_key`` constraint makes a repeated confirmed send
idempotent (AUT-039, AUT-184); foreign keys tie the row to the existing entities
and the audit event (AUT-233). SQLite triggers reject UPDATE/DELETE on
``publication_event`` so the lifecycle history is never rewritten (AUT-141).
Money is a decimal string and timestamps ISO-8601 UTC (AUT-231, AUT-232).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0017_publication"
down_revision: str | None = "0016_ai_input_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"

_TRIGGER_NO_UPDATE = "trg_publication_event_no_update"
_TRIGGER_NO_DELETE = "trg_publication_event_no_delete"


def upgrade() -> None:
    op.create_table(
        "publication",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(length=64),
            sa.ForeignKey("opportunity.id"),
            nullable=False,
        ),
        sa.Column(
            "content_generation_id",
            sa.String(length=64),
            sa.ForeignKey("content_generation.id"),
            nullable=False,
        ),
        sa.Column(
            "affiliate_link_id",
            sa.String(length=64),
            sa.ForeignKey("affiliate_link.id"),
            nullable=False,
        ),
        sa.Column("brand", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("destination_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("external_message_id", sa.String(length=256), nullable=True),
        sa.Column("published_price", sa.String(length=32), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column(
            "audit_event_id",
            sa.String(length=64),
            sa.ForeignKey("audit_event.id"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("published_at", sa.String(length=40), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_publication_idempotency_key"),
    )
    op.create_index(
        "ix_publication_opportunity",
        "publication",
        ["opportunity_id", "created_at"],
    )
    op.create_index(
        "ix_publication_published",
        "publication",
        ["status", "published_at"],
    )
    op.create_table(
        "publication_event",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "publication_id",
            sa.String(length=64),
            sa.ForeignKey("publication.id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.String(length=40), nullable=False),
    )
    op.create_index(
        "ix_publication_event_publication",
        "publication_event",
        ["publication_id", "occurred_at"],
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_publication_event_no_update "
            "BEFORE UPDATE ON publication_event "
            "BEGIN SELECT RAISE(ABORT, 'publication_event is append-only'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_publication_event_no_delete "
            "BEFORE DELETE ON publication_event "
            "BEGIN SELECT RAISE(ABORT, 'publication_event is append-only'); END"
        )
    )
    op.execute(
        sa.text(
            "UPDATE schema_version SET version = :version, recorded_at = :recorded_at "
            "WHERE component = :component"
        ).bindparams(
            version=revision,
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            component=DB_SCHEMA_COMPONENT,
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER_NO_UPDATE}"))
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER_NO_DELETE}"))
    op.drop_index("ix_publication_event_publication", table_name="publication_event")
    op.drop_table("publication_event")
    op.drop_index("ix_publication_published", table_name="publication")
    op.drop_index("ix_publication_opportunity", table_name="publication")
    op.drop_table("publication")
    op.execute(
        sa.text(
            "UPDATE schema_version SET version = :version, recorded_at = :recorded_at "
            "WHERE component = :component"
        ).bindparams(
            version=down_revision,
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            component=DB_SCHEMA_COMPONENT,
        )
    )
