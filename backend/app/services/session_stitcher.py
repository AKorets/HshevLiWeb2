"""Session stitching: merge GA4 midnight-boundary session splits.

GA4 resets ga_session_id at midnight local time. If the same ga_client_id
produced a new ga_session_id within 30 minutes of the previous session's
last_seen_at, we stitch them by updating the existing session row instead
of creating a new one.
"""

from __future__ import annotations
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_STITCH_WINDOW_MINUTES = 30


async def find_stitchable_session(
    db: AsyncSession,
    ga_client_id: str,
    environment: str,
) -> str | None:
    """Return the ID of a recent session that can be stitched, or None."""
    result = await db.execute(
        text(
            f"""
            SELECT id FROM sessions
            WHERE ga_client_id = :ga_client_id
              AND environment = :environment
              AND last_seen_at > now() - INTERVAL '{_STITCH_WINDOW_MINUTES} minutes'
            ORDER BY last_seen_at DESC
            LIMIT 1
            """
        ),
        {"ga_client_id": ga_client_id, "environment": environment},
    )
    row = result.fetchone()
    return str(row.id) if row else None


async def stitch_session(
    db: AsyncSession,
    session_id: str,
    new_ga_session_id: str,
) -> None:
    """Update an existing session row with the new ga_session_id and refresh last_seen_at."""
    await db.execute(
        text(
            "UPDATE sessions SET ga_session_id = :new_sid, last_seen_at = now() "
            "WHERE id = :id"
        ),
        {"new_sid": new_ga_session_id, "id": session_id},
    )
    logger.info(
        "session_stitched session_id=%s new_ga_session_id=%s",
        session_id,
        new_ga_session_id,
    )
