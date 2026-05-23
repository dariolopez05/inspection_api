"""create inspections table

Revision ID: 0001
Revises:
Create Date: 2026-05-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inspections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plate_number", sa.String(length=16), nullable=False),
        sa.Column("is_damaged", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_inspections_plate_number", "inspections", ["plate_number"])


def downgrade() -> None:
    op.drop_index("ix_inspections_plate_number", table_name="inspections")
    op.drop_table("inspections")
