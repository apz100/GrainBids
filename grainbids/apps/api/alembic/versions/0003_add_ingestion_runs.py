"""add ingestion runs and normalized price source fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_identifier", sa.String(length=1000), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
        sa.Column("raw_row_count", sa.BigInteger(), nullable=True),
        sa.Column("normalized_row_count", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
    )

    op.add_column("normalized_prices", sa.Column("source_name", sa.String(length=200), nullable=True))
    op.add_column("normalized_prices", sa.Column("delivery_start", sa.String(length=50), nullable=True))
    op.add_column("normalized_prices", sa.Column("delivery_end", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("normalized_prices", "delivery_end")
    op.drop_column("normalized_prices", "delivery_start")
    op.drop_column("normalized_prices", "source_name")
    op.drop_table("ingestion_runs")
