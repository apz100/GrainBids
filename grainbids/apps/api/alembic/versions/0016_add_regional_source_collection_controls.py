"""add regional source collection controls

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("country_code", sa.String(length=2), nullable=True))
    op.add_column("sources", sa.Column("currency_code", sa.String(length=3), nullable=True))
    op.add_column("sources", sa.Column("timezone_name", sa.String(length=100), nullable=True))
    op.add_column(
        "sources",
        sa.Column("collection_status", sa.String(length=30), nullable=False, server_default="candidate"),
    )
    op.execute(
        """
        UPDATE sources
        SET collection_status = 'pilot'
        WHERE source_type = 'automated'
          AND adapter_key IN ('agricharts', 'glg', 'hensall', 'snobelen', 'andersons')
        """
    )


def downgrade() -> None:
    op.drop_column("sources", "collection_status")
    op.drop_column("sources", "timezone_name")
    op.drop_column("sources", "currency_code")
    op.drop_column("sources", "country_code")
