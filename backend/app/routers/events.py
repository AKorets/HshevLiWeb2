"""POST /events — thin ingest for user_events."""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_factory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["events"])

# input_changed events require these keys in event_params
_REQUIRED_PARAMS: dict[str, set[str]] = {
    "input_changed": {"currency", "amount_entered"},
    "calculation_error": {"error_code"},
    "api_error": {"endpoint", "http_status"},
    "ui_crash": {"widget", "error_type"},
}

# input_changed backfill window (seconds)
_BACKFILL_WINDOW = 30


class EventIn(BaseModel):
    session_id: str
    user_id: str
    event_name: str
    event_params: dict = {}
    occurred_at: datetime | None = None
    tab_id: str | None = None


async def _get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


@router.post("", status_code=201)
async def ingest_event(
    body: EventIn,
    x_tab_id: str | None = Header(None, alias="X-Tab-Id"),
    db: AsyncSession = Depends(_get_session),
):
    # Validate required params for known event schemas
    required = _REQUIRED_PARAMS.get(body.event_name)
    if required:
        missing = required - set(body.event_params.keys())
        if missing:
            raise HTTPException(
                422,
                detail=f"event_params missing required keys for {body.event_name}: {sorted(missing)}",
            )

    tab_id = body.tab_id or x_tab_id
    result = await db.execute(
        text(
            """
            INSERT INTO user_events (session_id, user_id, event_name, event_params, occurred_at, tab_id)
            VALUES (:session_id, :user_id, :event_name, :event_params, COALESCE(:occurred_at, now()), :tab_id)
            RETURNING id
            """
        ),
        {
            "session_id": body.session_id,
            "user_id": body.user_id,
            "event_name": body.event_name,
            "event_params": body.event_params,
            "occurred_at": body.occurred_at,
            "tab_id": tab_id,
        },
    )
    event_id = result.scalar_one()
    await db.commit()

    # Schedule backfill for input_changed events
    if body.event_name == "input_changed":
        asyncio.create_task(
            _backfill_followed_by_calculate(
                event_id, body.session_id, tab_id, body.event_params
            )
        )

    return {"event_id": event_id}


async def _backfill_followed_by_calculate(
    event_id: int,
    session_id: str,
    tab_id: str | None,
    event_params: dict,
) -> None:
    await asyncio.sleep(_BACKFILL_WINDOW)
    factory = get_session_factory()
    async with factory() as db:
        try:
            result = await db.execute(
                text(
                    """
                    SELECT id FROM calculations
                    WHERE session_id = :session_id
                      AND (:tab_id IS NULL OR tab_id = :tab_id)
                      AND created_at > now() - INTERVAL '60 seconds'
                    LIMIT 1
                    """
                ),
                {"session_id": session_id, "tab_id": tab_id},
            )
            if result.fetchone():
                updated_params = {**event_params, "followed_by_calculate": True}
                await db.execute(
                    text(
                        "UPDATE user_events SET event_params = :params WHERE id = :id"
                    ),
                    {"params": updated_params, "id": event_id},
                )
                await db.commit()
                logger.info("Backfilled followed_by_calculate=true for event_id=%d", event_id)
        except Exception as exc:
            logger.warning("Backfill failed for event_id=%d: %s", event_id, exc)
