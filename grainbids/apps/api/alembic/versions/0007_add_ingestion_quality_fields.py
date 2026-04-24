"""add ingestion quality fields

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("duplicate_key_count", sa.BigInteger(), nullable=True))
    op.add_column("ingestion_runs", sa.Column("rejected_row_count", sa.BigInteger(), nullable=True))
    op.add_column("ingestion_runs", sa.Column("missing_required_count", sa.BigInteger(), nullable=True))
    op.add_column("ingestion_runs", sa.Column("row_reject_reasons_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_runs", "row_reject_reasons_json")
    op.drop_column("ingestion_runs", "missing_required_count")
    op.drop_column("ingestion_runs", "rejected_row_count")
    op.drop_column("ingestion_runs", "duplicate_key_count")
