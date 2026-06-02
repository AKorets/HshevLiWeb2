"""app_settings table with rates_fallback seed

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-03

Stores runtime-configurable key/value settings that can be changed
without redeploying. The rates_fallback row controls whether the rates
cache fetches from the free open.er-api.com fallback (true) or the
paid XE API (false).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("key"),
    )

    op.execute(
        "INSERT INTO app_settings (key, value) VALUES ('rates_fallback', 'true')"
        " ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("app_settings")
