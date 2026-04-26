"""saved_deals, telegram_deal_sends, user_events

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-24

Phase 3: saved_deals, telegram_deal_sends, user_events (partitioned).
user_events is monthly range-partitioned on occurred_at.
"""

from typing import Sequence, Union
from datetime import date

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_partition(table: str, year: int, month: int) -> None:
    if month == 12:
        end_year, end_month = year + 1, 1
    else:
        end_year, end_month = year, month + 1
    start = date(year, month, 1).isoformat()
    end = date(end_year, end_month, 1).isoformat()
    name = f"{table}_{year}_{month:02d}"
    op.execute(
        f"CREATE TABLE IF NOT EXISTS {name} "
        f"PARTITION OF {table} "
        f"FOR VALUES FROM ('{start}') TO ('{end}')"
    )


def upgrade() -> None:
    # --- saved_deals ---
    op.create_table(
        "saved_deals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("calculation_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Mirrors calculations.created_at — required because calculations is
        # partitioned and the FK must reference the full PK (id, created_at).
        sa.Column(
            "calculation_created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_type", sa.Text(), nullable=False, server_default="exchange"),
        sa.Column("headline_sell_currency", sa.Text(), nullable=True),
        sa.Column("headline_buy_currency", sa.Text(), nullable=True),
        sa.Column("headline_sell_amount", sa.Numeric(20, 8), nullable=True),
        sa.Column("headline_receive_amount", sa.Numeric(20, 8), nullable=True),
        sa.Column("tax_percent", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column(
            "saved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["calculation_id", "calculation_created_at"],
            ["calculations.id", "calculations.created_at"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_saved_deals_user_id", "saved_deals", ["user_id"])
    op.create_index("ix_saved_deals_saved_at", "saved_deals", ["saved_at"])
    op.execute(
        "COMMENT ON TABLE saved_deals IS "
        "'User-initiated deal save. References the originating calculation. "
        "headline_* fields are denormalized from the dominant calculation line for list views.'"
    )
    op.execute(
        "COMMENT ON COLUMN saved_deals.deal_type IS "
        "'Always exchange for now; kept for compatibility with issue #129.'"
    )

    # --- telegram_deal_sends ---
    op.create_table(
        "telegram_deal_sends",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("saved_deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.Text(), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["saved_deal_id"], ["saved_deals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "status IN ('sent','failed','rate_limited','retrying')",
            name="ck_tg_sends_status",
        ),
    )
    op.create_index(
        "ix_telegram_deal_sends_saved_deal_id",
        "telegram_deal_sends",
        ["saved_deal_id"],
    )
    op.create_index(
        "ix_telegram_deal_sends_user_id", "telegram_deal_sends", ["user_id"]
    )
    op.create_index(
        "ix_telegram_deal_sends_sent_at", "telegram_deal_sends", ["sent_at"]
    )
    op.create_index(
        "ix_telegram_deal_sends_status", "telegram_deal_sends", ["status"]
    )
    op.execute(
        "COMMENT ON TABLE telegram_deal_sends IS "
        "'Append-only log of Telegram share attempts. "
        "telegram_username is a display snapshot at send time — never used for delivery.'"
    )

    # --- user_events (monthly partitioned on occurred_at) ---
    op.execute(
        """
        CREATE TABLE user_events (
            id          BIGSERIAL     NOT NULL,
            session_id  UUID          NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
            user_id     UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            event_name  TEXT          NOT NULL,
            event_params JSONB        NOT NULL DEFAULT '{}'::jsonb,
            occurred_at TIMESTAMPTZ   NOT NULL DEFAULT now(),
            tab_id      TEXT          NULL,
            PRIMARY KEY (id, occurred_at)
        ) PARTITION BY RANGE (occurred_at)
        """
    )
    op.execute(
        "CREATE INDEX ix_user_events_session_id ON user_events (session_id, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_user_events_user_id ON user_events (user_id, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_user_events_occurred_at ON user_events (occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_user_events_event_name ON user_events (event_name, occurred_at)"
    )

    # Pre-create partitions
    today = date.today()
    for delta in range(3):
        m = today.month + delta
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        _create_partition("user_events", y, m)

    op.execute("CREATE TABLE user_events_default PARTITION OF user_events DEFAULT")

    op.execute(
        "COMMENT ON TABLE user_events IS "
        "'Append-only server-side mirror of key GA4 events. "
        "event_params JSONB must not contain free-text PII. "
        "tab_id correlates events to a specific browser tab within a session.'"
    )
    op.execute(
        "COMMENT ON COLUMN user_events.event_name IS "
        "'Canonical event names: calculate, deal_saved, deal_shared, rates_refreshed, "
        "tab_changed, input_changed, calculation_error, api_error, ui_crash.'"
    )
    op.execute(
        "COMMENT ON COLUMN user_events.tab_id IS "
        "'sessionStorage UUID per browser tab (from X-Tab-Id request header). "
        "NULL for server-generated events.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_events_default")
    today = date.today()
    for delta in range(3):
        m = today.month + delta
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        op.execute(f"DROP TABLE IF EXISTS user_events_{y}_{m:02d}")
    op.execute("DROP TABLE IF EXISTS user_events")

    op.drop_index("ix_telegram_deal_sends_status", table_name="telegram_deal_sends")
    op.drop_index("ix_telegram_deal_sends_sent_at", table_name="telegram_deal_sends")
    op.drop_index("ix_telegram_deal_sends_user_id", table_name="telegram_deal_sends")
    op.drop_index("ix_telegram_deal_sends_saved_deal_id", table_name="telegram_deal_sends")
    op.drop_table("telegram_deal_sends")

    op.drop_index("ix_saved_deals_saved_at", table_name="saved_deals")
    op.drop_index("ix_saved_deals_user_id", table_name="saved_deals")
    op.drop_table("saved_deals")
