"""add basis change strict + carry timestamp fields

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("normalized_prices", sa.Column("basis_change_strict", sa.Numeric(18, 6), nullable=True))
    op.add_column("normalized_prices", sa.Column("basis_last_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("normalized_prices", "basis_last_changed_at")
    op.drop_column("normalized_prices", "basis_change_strict")

