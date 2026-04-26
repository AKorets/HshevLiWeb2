"""calculations and calculation_lines — monthly range-partitioned

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-24

Phase 2: calculations (monthly partitioned on created_at) and calculation_lines.
Adds client_calculated_at, client_request_id, tab_id, experiment_flags, is_offline_sync.
Pre-creates partitions for the current month and two months ahead.
"""

from typing import Sequence, Union
from datetime import date, timedelta

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _month_range(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


def _create_partition(table: str, year: int, month: int) -> None:
    start, end = _month_range(year, month)
    name = f"{table}_{year}_{month:02d}"
    op.execute(
        f"CREATE TABLE IF NOT EXISTS {name} "
        f"PARTITION OF {table} "
        f"FOR VALUES FROM ('{start}') TO ('{end}')"
    )


def upgrade() -> None:
    # --- calculations (partitioned by range on created_at) ---
    op.execute(
        """
        CREATE TABLE calculations (
            id              UUID          NOT NULL DEFAULT gen_random_uuid(),
            session_id      UUID          NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
            user_id         UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            rate_snapshot_id INTEGER      NOT NULL REFERENCES rate_snapshots(id),
            fee_mode        TEXT          NOT NULL,
            total_gross_usdt NUMERIC(20,8) NOT NULL,
            total_fee_usdt  NUMERIC(20,8) NOT NULL,
            total_net_usdt  NUMERIC(20,8) NOT NULL,
            ils_equivalent  NUMERIC(20,2) NOT NULL,
            above_min_threshold BOOLEAN   NOT NULL,
            currencies      TEXT[]        NOT NULL,
            is_saved        BOOLEAN       NOT NULL DEFAULT FALSE,
            ga_client_id    TEXT          NOT NULL,
            ga_session_id   TEXT          NOT NULL,
            created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
            retention_bucket TEXT         NOT NULL DEFAULT 'standard',
            client_calculated_at TIMESTAMPTZ NULL,
            client_request_id UUID        NULL,
            tab_id          TEXT          NULL,
            experiment_flags JSONB        NULL,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
        """
    )

    # Unique index on (client_request_id, created_at). The partition key
    # (created_at) must be in any UNIQUE index on a partitioned table — see
    # https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITIONING-DECLARATIVE-LIMITATIONS
    # Trade-off: idempotency only holds within a single monthly partition.
    op.execute(
        "CREATE UNIQUE INDEX uq_calculations_client_request_id "
        "ON calculations (client_request_id, created_at) "
        "WHERE client_request_id IS NOT NULL"
    )

    # Regular indexes
    op.execute("CREATE INDEX ix_calculations_user_id ON calculations (user_id, created_at)")
    op.execute("CREATE INDEX ix_calculations_session_id ON calculations (session_id, created_at)")
    op.execute("CREATE INDEX ix_calculations_created_at ON calculations (created_at)")
    op.execute("CREATE INDEX ix_calculations_ils_equivalent ON calculations (ils_equivalent, created_at)")
    op.execute("CREATE INDEX ix_calculations_client_request_id ON calculations (client_request_id) WHERE client_request_id IS NOT NULL")
    op.execute("CREATE INDEX ix_calculations_currencies_gin ON calculations USING GIN (currencies)")

    # Pre-create partitions for current month + 2 ahead
    today = date.today()
    for delta in range(3):
        m = today.month + delta
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        _create_partition("calculations", y, m)

    # Default partition for overflow
    op.execute(
        "CREATE TABLE calculations_default "
        "PARTITION OF calculations DEFAULT"
    )

    op.execute(
        "COMMENT ON TABLE calculations IS "
        "'One row per calculator run (not just saved deals). "
        "Monthly range-partitioned on created_at. "
        "client_request_id enables idempotent ingest on Flutter retry.'"
    )
    op.execute(
        "COMMENT ON COLUMN calculations.above_min_threshold IS "
        "'Cached flag: ils_equivalent >= 50000 (large-deal signal).'"
    )
    op.execute(
        "COMMENT ON COLUMN calculations.client_calculated_at IS "
        "'Timestamp captured on the client at the moment Calculate was pressed. "
        "Differs from created_at for offline/PWA-cached calculations.'"
    )
    op.execute(
        "COMMENT ON COLUMN calculations.client_request_id IS "
        "'UUID generated by the Flutter client for idempotency. "
        "Duplicate submissions with the same value are silently ignored.'"
    )
    op.execute(
        "COMMENT ON COLUMN calculations.tab_id IS "
        "'Per-tab sessionStorage UUID. Disambiguates calculations from "
        "multiple open browser tabs sharing the same GA4 session_id.'"
    )
    op.execute(
        "COMMENT ON COLUMN calculations.experiment_flags IS "
        "'Snapshot of A/B flags active at calculation time.'"
    )

    # --- calculation_lines ---
    op.create_table(
        "calculation_lines",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("calculation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_index", sa.SmallInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("fee_percent", sa.Numeric(6, 3), nullable=False),
        sa.Column("gross_usdt", sa.Numeric(20, 8), nullable=False),
        sa.Column("fee_usdt", sa.Numeric(20, 8), nullable=False),
        sa.Column("net_usdt", sa.Numeric(20, 8), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["calculation_id"],
            ["calculations.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_calc_lines_calc_id", "calculation_lines", ["calculation_id"])
    op.create_index("ix_calc_lines_currency", "calculation_lines", ["currency"])
    op.execute(
        "COMMENT ON TABLE calculation_lines IS "
        "'Line-level detail for each calculation, mirroring DealLine. "
        "One row per currency input per calculation.'"
    )


def downgrade() -> None:
    op.drop_index("ix_calc_lines_currency", table_name="calculation_lines")
    op.drop_index("ix_calc_lines_calc_id", table_name="calculation_lines")
    op.drop_table("calculation_lines")

    # Drop partitions before the parent
    op.execute("DROP TABLE IF EXISTS calculations_default")
    today = date.today()
    for delta in range(3):
        m = today.month + delta
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        op.execute(f"DROP TABLE IF EXISTS calculations_{y}_{m:02d}")

    op.execute("DROP TABLE IF EXISTS calculations")
