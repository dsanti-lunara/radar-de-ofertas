"""append-only price observation history

Revision ID: 0003_price_observation
Revises: 0002_manual_capture
Create Date: 2026-10-05

Introduces the append-only ``price_observation`` table (RDR-013, AUT-028). Each
row is one monetary observation of a ``marketplace_product`` at an instant,
sourced from a capture. Money is stored as decimal strings and timestamps as
ISO-8601 UTC strings (AUT-231, AUT-232). The documented identity
``(marketplace_product_id, source, observed_at)`` is enforced by a unique
constraint, and foreign keys tie the observation to its product and raw capture,
which SQLite enforces (AUT-233).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0003_price_observation"
down_revision: str | None = "0002_manual_capture"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.create_table(
        "price_observation",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("marketplace_product_id", sa.String(length=64), nullable=False),
        sa.Column("price", sa.String(length=40), nullable=False),
        sa.Column("original_price", sa.String(length=40), nullable=True),
        sa.Column("shipping_cost", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.String(length=40), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("raw_capture_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["marketplace_product_id"], ["marketplace_product.id"]),
        sa.ForeignKeyConstraint(["raw_capture_id"], ["raw_capture.id"]),
        sa.UniqueConstraint(
            "marketplace_product_id",
            "source",
            "observed_at",
            name="uq_price_observation_identity",
        ),
    )
    op.create_index(
        "ix_price_observation_product_observed",
        "price_observation",
        ["marketplace_product_id", "observed_at"],
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
    op.drop_index("ix_price_observation_product_observed", table_name="price_observation")
    op.drop_table("price_observation")
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
