"""add futures change column to normalized prices

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("normalized_prices", sa.Column("futures_change", sa.Numeric(18, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("normalized_prices", "futures_change")
