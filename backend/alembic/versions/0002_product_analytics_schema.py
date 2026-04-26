"""product analytics schema — identity and session tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24

Phase 1: users, user_uuids, oauth_identities, telegram_identities, sessions.
Includes device/geo context, experiment flags, soft-delete, consecutive_errors.
Extensions: pgcrypto, pg_trgm, pgvector.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Extensions ---
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- users ---
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("consent_pii", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "retention_bucket",
            sa.Text(),
            nullable=False,
            server_default="standard",
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('anonymous','oauth','deleted')", name="ck_users_kind"),
    )
    op.create_index("ix_users_created_at", "users", ["created_at"])
    op.execute(
        "COMMENT ON TABLE users IS "
        "'One row per logical human identity (anonymous or OAuth-backed).'"
    )
    op.execute(
        "COMMENT ON COLUMN users.kind IS "
        "'anonymous = device-UUID only; oauth = linked OAuth provider; deleted = soft-deleted'"
    )
    op.execute(
        "COMMENT ON COLUMN users.consent_pii IS "
        "'True when the user has given explicit consent to store PII (e.g. email).'"
    )
    op.execute(
        "COMMENT ON COLUMN users.retention_bucket IS "
        "'Data-retention tier: standard (25 months), minimal (90 days).'"
    )
    op.execute(
        "COMMENT ON COLUMN users.deleted_at IS "
        "'Soft-delete timestamp. Non-null means the account is deactivated. '"
        "PII is anonymised 30 days after this is set.'"
    )

    # --- user_uuids ---
    op.create_table(
        "user_uuids",
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("uuid"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_user_uuids_user_id", "user_uuids", ["user_id"])
    op.execute(
        "COMMENT ON TABLE user_uuids IS "
        "'Device/browser UUIDs (localStorage) owned by a user — many-to-one with users.'"
    )

    # --- oauth_identities ---
    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_subject", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_oauth_provider_subject"),
        sa.CheckConstraint("provider IN ('google','apple')", name="ck_oauth_provider"),
    )
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"])
    op.execute(
        "COMMENT ON TABLE oauth_identities IS "
        "'OAuth provider bindings (Google, Apple) for a user row.'"
    )
    op.execute(
        "COMMENT ON COLUMN oauth_identities.email IS "
        "'Populated only when users.consent_pii = TRUE at link time.'"
    )

    # --- telegram_identities ---
    op.create_table(
        "telegram_identities",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("telegram_username", sa.Text(), nullable=True),
        sa.Column("telegram_first_name", sa.Text(), nullable=True),
        sa.Column("telegram_last_name", sa.Text(), nullable=True),
        sa.Column("telegram_language_code", sa.Text(), nullable=True),
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "consecutive_errors",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_telegram_identities_user_id", "telegram_identities", ["user_id"])
    op.create_index(
        "ix_telegram_identities_username",
        "telegram_identities",
        ["telegram_username"],
        postgresql_where=sa.text("telegram_username IS NOT NULL"),
    )
    op.execute(
        "COMMENT ON TABLE telegram_identities IS "
        "'Telegram bot connection for a user. Unique by telegram_chat_id. '"
        "Outbound messages always use telegram_chat_id, never telegram_username.'"
    )
    op.execute(
        "COMMENT ON COLUMN telegram_identities.consecutive_errors IS "
        "'Incremented on each failed send; is_active set to FALSE when >= 3.'"
    )

    # --- sessions ---
    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_uuid",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("ga_client_id", sa.Text(), nullable=False),
        sa.Column("ga_session_id", sa.Text(), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("utm_source", sa.Text(), nullable=True),
        sa.Column("utm_medium", sa.Text(), nullable=True),
        sa.Column("utm_campaign", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.LargeBinary(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "retention_bucket",
            sa.Text(),
            nullable=False,
            server_default="standard",
        ),
        # Device context (G5)
        sa.Column("device_type", sa.Text(), nullable=True),
        sa.Column("os_family", sa.Text(), nullable=True),
        sa.Column("browser_family", sa.Text(), nullable=True),
        sa.Column("screen_width", sa.SmallInteger(), nullable=True),
        sa.Column("screen_height", sa.SmallInteger(), nullable=True),
        sa.Column("viewport_width", sa.SmallInteger(), nullable=True),
        sa.Column("viewport_height", sa.SmallInteger(), nullable=True),
        sa.Column("device_pixel_ratio", sa.Numeric(4, 2), nullable=True),
        sa.Column("cpu_cores", sa.SmallInteger(), nullable=True),
        sa.Column("device_memory_gb", sa.Numeric(4, 1), nullable=True),
        # Network & geo (G6, G7)
        sa.Column("country_code", sa.CHAR(2), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("isp", sa.Text(), nullable=True),
        sa.Column("connection_type", sa.Text(), nullable=True),
        # Experiments (G4)
        sa.Column(
            "experiment_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["user_uuid"], ["user_uuids.uuid"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "environment IN ('prod','staging','demo')", name="ck_sessions_env"
        ),
        sa.CheckConstraint(
            "device_type IN ('desktop','mobile','tablet','unknown') OR device_type IS NULL",
            name="ck_sessions_device_type",
        ),
        sa.CheckConstraint(
            "connection_type IN ('wifi','ethernet','4g','3g','2g','unknown') OR connection_type IS NULL",
            name="ck_sessions_connection_type",
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_ga_client_id", "sessions", ["ga_client_id"])
    op.create_index("ix_sessions_ga_session_id", "sessions", ["ga_session_id"])
    op.create_index("ix_sessions_first_seen_at", "sessions", ["first_seen_at"])
    op.create_index("ix_sessions_country_code", "sessions", ["country_code"])
    op.create_index("ix_sessions_device_type", "sessions", ["device_type"])
    op.execute(
        "CREATE INDEX ix_sessions_experiment_flags_gin "
        "ON sessions USING GIN (experiment_flags)"
    )
    op.execute(
        "COMMENT ON TABLE sessions IS "
        "'One row per GA4 session (keyed by ga_client_id + ga_session_id + environment). '"
        "Carries device, geo, UTM, and experiment context for zero-join analytics.'"
    )
    op.execute(
        "COMMENT ON COLUMN sessions.ga_client_id IS "
        "'GA4 client_id from gtag getter API — used to correlate with BigQuery export.'"
    )
    op.execute(
        "COMMENT ON COLUMN sessions.ga_session_id IS "
        "'GA4 session_id; resets at midnight local time (see session stitching in Phase 11).'"
    )
    op.execute(
        "COMMENT ON COLUMN sessions.ip_hash IS "
        "'Salted SHA-256 of the raw IP (salt from GA_IP_HASH_SALT env var). Raw IP never stored.'"
    )
    op.execute(
        "COMMENT ON COLUMN sessions.experiment_flags IS "
        "'A/B experiment variant map, e.g. {\"fee_ui_v2\": \"treatment\"}.'"
    )
    op.execute(
        "COMMENT ON COLUMN sessions.consecutive_errors IS "
        "'Not on sessions — see telegram_identities.'"
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_experiment_flags_gin", table_name="sessions")
    op.drop_index("ix_sessions_device_type", table_name="sessions")
    op.drop_index("ix_sessions_country_code", table_name="sessions")
    op.drop_index("ix_sessions_first_seen_at", table_name="sessions")
    op.drop_index("ix_sessions_ga_session_id", table_name="sessions")
    op.drop_index("ix_sessions_ga_client_id", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index(
        "ix_telegram_identities_username", table_name="telegram_identities"
    )
    op.drop_index(
        "ix_telegram_identities_user_id", table_name="telegram_identities"
    )
    op.drop_table("telegram_identities")

    op.drop_index("ix_oauth_identities_user_id", table_name="oauth_identities")
    op.drop_table("oauth_identities")

    op.drop_index("ix_user_uuids_user_id", table_name="user_uuids")
    op.drop_table("user_uuids")

    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_table("users")

    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
