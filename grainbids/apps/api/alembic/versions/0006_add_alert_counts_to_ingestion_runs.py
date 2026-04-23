"""add alert count metrics to ingestion runs

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("created_alert_count", sa.BigInteger(), nullable=True))
    op.add_column("ingestion_runs", sa.Column("deduped_alert_count", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_runs", "deduped_alert_count")
    op.drop_column("ingestion_runs", "created_alert_count")
