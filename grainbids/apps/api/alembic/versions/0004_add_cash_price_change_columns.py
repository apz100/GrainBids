"""add cash price change columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-21
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("normalized_prices", sa.Column("cash_price_bu_change", sa.Numeric(18, 6), nullable=True))
    op.add_column("normalized_prices", sa.Column("cash_price_mt_change", sa.Numeric(18, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("normalized_prices", "cash_price_mt_change")
    op.drop_column("normalized_prices", "cash_price_bu_change")
