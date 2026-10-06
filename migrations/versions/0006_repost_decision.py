"""append-only repost decision

Revision ID: 0006_repost_decision
Revises: 0005_purchase_source_decision
Create Date: 2026-10-05

Introduces the append-only ``repost_decision`` table (RDR-033, AUT-029,
AUT-064). Each row records one dedupe/repost guardrail decision: the decision and
reason, the material changes and warnings as JSON, the publication baseline used
for the comparison, the observed price drop, the cooldown window and the
versioned policy it was computed from. Money is stored as decimal strings and
timestamps as ISO-8601 UTC strings (AUT-231, AUT-232). SQLite triggers reject any
UPDATE or DELETE so a recorded decision is never overwritten, and foreign keys
tie the row to its Candidate and audit event (AUT-233).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0006_repost_decision"
down_revision: str | None = "0005_purchase_source_decision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"

_TRIGGER_NO_UPDATE = "trg_repost_decision_no_update"
_TRIGGER_NO_DELETE = "trg_repost_decision_no_delete"


def upgrade() -> None:
    op.create_table(
        "repost_decision",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=48), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("material_changes", sa.Text(), nullable=False),
        sa.Column("publication", sa.Text(), nullable=True),
        sa.Column("current_price", sa.String(length=40), nullable=False),
        sa.Column("observed_price_drop_percent", sa.String(length=40), nullable=True),
        sa.Column("cooldown_expires_at", sa.String(length=40), nullable=True),
        sa.Column("cooldown_expired", sa.Boolean(), nullable=False),
        sa.Column("deal_score", sa.String(length=40), nullable=True),
        sa.Column("policy", sa.Text(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False),
        sa.Column("as_of", sa.String(length=40), nullable=False),
        sa.Column("audit_event_id", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate.id"]),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_event.id"]),
    )
    op.create_index(
        "ix_repost_decision_candidate_created",
        "repost_decision",
        ["candidate_id", "created_at"],
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_repost_decision_no_update "
            "BEFORE UPDATE ON repost_decision "
            "BEGIN SELECT RAISE(ABORT, 'repost decision is append-only'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_repost_decision_no_delete "
            "BEFORE DELETE ON repost_decision "
            "BEGIN SELECT RAISE(ABORT, 'repost decision is append-only'); END"
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
    op.drop_index(
        "ix_repost_decision_candidate_created",
        table_name="repost_decision",
    )
    op.drop_table("repost_decision")
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
