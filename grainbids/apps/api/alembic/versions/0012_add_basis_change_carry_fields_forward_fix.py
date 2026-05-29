"""forward-fix basis carry fields for environments already stamped at 0011

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name, schema="public")
    return {str(column["name"]) for column in columns}


def upgrade() -> None:
    op.execute("SET LOCAL statement_timeout = 0")
    columns = _column_names("normalized_prices")
    if "basis_change_strict" not in columns:
        op.add_column("normalized_prices", sa.Column("basis_change_strict", sa.Numeric(18, 6), nullable=True))
    if "basis_last_changed_at" not in columns:
        op.add_column("normalized_prices", sa.Column("basis_last_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.execute("SET LOCAL statement_timeout = 0")
    columns = _column_names("normalized_prices")
    if "basis_last_changed_at" in columns:
        op.drop_column("normalized_prices", "basis_last_changed_at")
    if "basis_change_strict" in columns:
        op.drop_column("normalized_prices", "basis_change_strict")
