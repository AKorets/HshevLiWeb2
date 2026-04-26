"""user_merges table for anon→OAuth identity audit trail

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24

Phase 8: user_merges (append-only log of anon→OAuth reassignments).
Deferred from Phase 1 as specified in the design decisions.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_merges",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("from_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "to_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "merge_reason",
            sa.Text(),
            nullable=False,
            server_default="oauth_link",
        ),
        sa.Column(
            "merged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["to_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_user_merges_to_user_id", "user_merges", ["to_user_id"])
    op.create_index("ix_user_merges_from_user_id", "user_merges", ["from_user_id"])
    op.execute(
        "COMMENT ON TABLE user_merges IS "
        "'Append-only audit trail of anonymous→OAuth identity reassignments. "
        "from_user_id is the anonymous user that was merged/retired.'"
    )
    op.execute(
        "COMMENT ON COLUMN user_merges.merge_reason IS "
        "'oauth_link: anonymous UUID matched to an OAuth identity; "
        "telegram_link: Telegram chat_id bound to a different user.'"
    )


def downgrade() -> None:
    op.drop_index("ix_user_merges_from_user_id", table_name="user_merges")
    op.drop_index("ix_user_merges_to_user_id", table_name="user_merges")
    op.drop_table("user_merges")
