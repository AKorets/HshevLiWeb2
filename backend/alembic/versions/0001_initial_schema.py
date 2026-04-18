"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ils_to_usdt", sa.Float(), nullable=False),
        sa.Column("usd_to_usdt", sa.Float(), nullable=False),
        sa.Column("euro_to_usdt", sa.Float(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_snapshots_fetched_at", "rate_snapshots", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_rate_snapshots_fetched_at", table_name="rate_snapshots")
    op.drop_table("rate_snapshots")
