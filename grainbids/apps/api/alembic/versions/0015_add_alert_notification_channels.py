"""add notification channels to alert rules

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_rules",
        sa.Column("notification_channels_json", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_rules", "notification_channels_json")
