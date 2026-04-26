"""session quality metrics and advanced signals

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-24

Phase 11: Adds scroll_depth_percent, time_to_first_action_ms,
hesitation_before_calc_ms, and device_fingerprint_hash to sessions.
Also adds a unique index on (ga_client_id, ga_session_id, environment)
to support efficient session stitching.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Session quality metrics
    op.add_column("sessions", sa.Column("scroll_depth_percent", sa.SmallInteger(), nullable=True))
    op.add_column("sessions", sa.Column("time_to_first_action_ms", sa.Integer(), nullable=True))
    op.add_column("sessions", sa.Column("hesitation_before_calc_ms", sa.Integer(), nullable=True))
    # Privacy-gated device fingerprint (consent-gated, hashed)
    op.add_column("sessions", sa.Column("device_fingerprint_hash", sa.LargeBinary(), nullable=True))

    # Unique constraint for session stitching upserts
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sessions_ga_composite "
        "ON sessions (ga_client_id, ga_session_id, environment)"
    )

    op.execute(
        "COMMENT ON COLUMN sessions.scroll_depth_percent IS "
        "'Maximum scroll depth reached in this session (0-100). Updated on heartbeat.'"
    )
    op.execute(
        "COMMENT ON COLUMN sessions.time_to_first_action_ms IS "
        "'Milliseconds from page load to first user interaction.'"
    )
    op.execute(
        "COMMENT ON COLUMN sessions.hesitation_before_calc_ms IS "
        "'Milliseconds between last input_changed event and Calculate press.'"
    )
    op.execute(
        "COMMENT ON COLUMN sessions.device_fingerprint_hash IS "
        "'Salted SHA-256 of canvas+WebGL fingerprint. Stored only when "
        "users.consent_pii = TRUE. Enables shared-device detection.'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sessions_ga_composite")
    op.drop_column("sessions", "device_fingerprint_hash")
    op.drop_column("sessions", "hesitation_before_calc_ms")
    op.drop_column("sessions", "time_to_first_action_ms")
    op.drop_column("sessions", "scroll_depth_percent")
