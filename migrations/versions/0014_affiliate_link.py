"""affiliate links generated for approved opportunities

Revision ID: 0014_affiliate_link
Revises: 0013_ai_review
Create Date: 2026-10-06

Introduces the ``affiliate_link`` table (RDR-018, RDR-070, AUT-033). Each row is
one independent, auditable link of an approved ``opportunity``: the literal
``affiliate_url`` returned by the provider (never rewritten), the generation
method, the status and the internal tracking context separated from the external
label (RECON-003). The ``uq_affiliate_link_opportunity_tracking`` unique
constraint makes generation idempotent for the same Opportunity + label
(AUT-039, AUT-132); ``opportunity_id`` and ``audit_event_id`` are real foreign
keys so an orphan link is impossible (AUT-233). Timestamps are ISO-8601 UTC
strings (AUT-231).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0014_affiliate_link"
down_revision: str | None = "0013_ai_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.create_table(
        "affiliate_link",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(length=64),
            sa.ForeignKey("opportunity.id"),
            nullable=False,
        ),
        sa.Column("marketplace", sa.String(length=32), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("affiliate_url", sa.Text(), nullable=False),
        sa.Column("generation_method", sa.String(length=32), nullable=False),
        sa.Column("productive", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("tracking_context_id", sa.String(length=64), nullable=False),
        sa.Column("tracking_label", sa.String(length=64), nullable=False),
        sa.Column("tracking_brand", sa.String(length=32), nullable=False),
        sa.Column("tracking_internal_reference", sa.String(length=128), nullable=False),
        sa.Column("tracking_mapping_version", sa.String(length=64), nullable=False),
        sa.Column("tracking_mapping_hash", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column(
            "audit_event_id",
            sa.String(length=64),
            sa.ForeignKey("audit_event.id"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint(
            "opportunity_id",
            "tracking_label",
            name="uq_affiliate_link_opportunity_tracking",
        ),
    )
    op.create_index(
        "ix_affiliate_link_opportunity",
        "affiliate_link",
        ["opportunity_id", "created_at"],
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
    op.drop_index("ix_affiliate_link_opportunity", table_name="affiliate_link")
    op.drop_table("affiliate_link")
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
