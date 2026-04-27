"""grant runtime role full DML on analytics tables + sequences

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-27

Background:
  Migrations run as the doadmin superuser (so they can CREATE SCHEMA
  mcp_readonly and run the role-management statements in 0005). Every
  table created by 0002–0007 is therefore owned by `doadmin`. The
  runtime backend connects as the lower-privilege `rates-db` role and
  has no implicit access to doadmin-owned objects.

  Result on prod: the heartbeat handler crashed with
    asyncpg.exceptions.InsufficientPrivilegeError: permission denied for
    table user_uuids
  …leaving sessions/calculations/user_events permanently empty even
  after PR #281 wired Flutter to fire /sessions/heartbeat.

  This migration grants the runtime role full DML on the public schema
  and sets default privileges so every future table created by doadmin
  is automatically grantable. Idempotent — safe to re-run.

Note on quoting:
  The runtime role is literally "rates-db" (with a hyphen). Postgres
  parses unquoted hyphens as the subtraction operator, so the role name
  must always appear inside double quotes in SQL.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RUNTIME_ROLE = '"rates-db"'


def upgrade() -> None:
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES '
        f'IN SCHEMA public TO {RUNTIME_ROLE}'
    )
    op.execute(
        f'GRANT USAGE, SELECT ON ALL SEQUENCES '
        f'IN SCHEMA public TO {RUNTIME_ROLE}'
    )
    op.execute(
        f'ALTER DEFAULT PRIVILEGES FOR ROLE doadmin IN SCHEMA public '
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {RUNTIME_ROLE}'
    )
    op.execute(
        f'ALTER DEFAULT PRIVILEGES FOR ROLE doadmin IN SCHEMA public '
        f'GRANT USAGE, SELECT ON SEQUENCES TO {RUNTIME_ROLE}'
    )


def downgrade() -> None:
    op.execute(
        f'ALTER DEFAULT PRIVILEGES FOR ROLE doadmin IN SCHEMA public '
        f'REVOKE USAGE, SELECT ON SEQUENCES FROM {RUNTIME_ROLE}'
    )
    op.execute(
        f'ALTER DEFAULT PRIVILEGES FOR ROLE doadmin IN SCHEMA public '
        f'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {RUNTIME_ROLE}'
    )
    op.execute(
        f'REVOKE USAGE, SELECT ON ALL SEQUENCES '
        f'IN SCHEMA public FROM {RUNTIME_ROLE}'
    )
    op.execute(
        f'REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES '
        f'IN SCHEMA public FROM {RUNTIME_ROLE}'
    )
