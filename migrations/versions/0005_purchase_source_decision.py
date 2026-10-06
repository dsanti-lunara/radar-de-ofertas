"""append-only purchase source decision

Revision ID: 0005_purchase_source_decision
Revises: 0004_evaluation
Create Date: 2026-10-05

Introduces the append-only ``purchase_source_decision`` table (RDR-031,
AUT-029). Each row records one purchase source guardrail decision: the chosen
affiliate source, the best reliable/equivalent alternative, the effective prices
and percentage difference, the decision, the source evaluations and warnings as
JSON, and the versioned policy it was computed from. Money is stored as decimal
strings and timestamps as ISO-8601 UTC strings (AUT-231, AUT-232). SQLite triggers
reject any UPDATE or DELETE so a recorded decision is never overwritten, and
foreign keys tie the row to its Candidate and audit event (AUT-233).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0005_purchase_source_decision"
down_revision: str | None = "0004_evaluation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"

_TRIGGER_NO_UPDATE = "trg_purchase_source_decision_no_update"
_TRIGGER_NO_DELETE = "trg_purchase_source_decision_no_delete"


def upgrade() -> None:
    op.create_table(
        "purchase_source_decision",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("chosen_source_id", sa.String(length=128), nullable=False),
        sa.Column("best_alternative_source_id", sa.String(length=128), nullable=True),
        sa.Column("substituted_source_id", sa.String(length=128), nullable=True),
        sa.Column("chosen_effective_price", sa.String(length=40), nullable=True),
        sa.Column("alternative_effective_price", sa.String(length=40), nullable=True),
        sa.Column("difference_percent", sa.String(length=40), nullable=True),
        sa.Column("material", sa.Boolean(), nullable=False),
        sa.Column("threshold_percent", sa.String(length=40), nullable=False),
        sa.Column("commission_considered", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_action", sa.String(length=16), nullable=False),
        sa.Column("sources", sa.Text(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False),
        sa.Column("as_of", sa.String(length=40), nullable=False),
        sa.Column("audit_event_id", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate.id"]),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_event.id"]),
    )
    op.create_index(
        "ix_purchase_source_decision_candidate_created",
        "purchase_source_decision",
        ["candidate_id", "created_at"],
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_purchase_source_decision_no_update "
            "BEFORE UPDATE ON purchase_source_decision "
            "BEGIN SELECT RAISE(ABORT, 'purchase source decision is append-only'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_purchase_source_decision_no_delete "
            "BEFORE DELETE ON purchase_source_decision "
            "BEGIN SELECT RAISE(ABORT, 'purchase source decision is append-only'); END"
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
        "ix_purchase_source_decision_candidate_created",
        table_name="purchase_source_decision",
    )
    op.drop_table("purchase_source_decision")
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
