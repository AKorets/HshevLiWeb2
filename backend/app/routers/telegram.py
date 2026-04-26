"""Telegram bot integration endpoints.

POST /telegram/connect  — deep-link webhook; binds telegram_chat_id to device UUID
POST /telegram/send-deal — render and send a saved deal; logs telegram_deal_sends
"""

from __future__ import annotations
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_factory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])

_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TG_CONSECUTIVE_ERROR_THRESHOLD = 3


class ConnectRequest(BaseModel):
    device_uuid: str
    telegram_chat_id: int
    telegram_username: str | None = None
    telegram_first_name: str | None = None
    telegram_last_name: str | None = None
    telegram_language_code: str | None = None


class SendDealRequest(BaseModel):
    saved_deal_id: str
    user_id: str
    telegram_chat_id: int
    message_text: str


async def _get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


@router.post("/connect", status_code=200)
async def connect_telegram(
    body: ConnectRequest,
    db: AsyncSession = Depends(_get_session),
):
    """Bind a Telegram chat_id to the user identified by device_uuid.

    Telegram wins: if telegram_chat_id is already bound to another user,
    reassign device_uuid to the Telegram-owning user and log a user_merge.
    """
    uuid_row = await db.execute(
        text("SELECT user_id FROM user_uuids WHERE uuid = :uuid"),
        {"uuid": body.device_uuid},
    )
    uuid_record = uuid_row.fetchone()
    if uuid_record is None:
        raise HTTPException(404, "device_uuid not found")
    device_user_id = uuid_record.user_id

    # Check if telegram_chat_id already bound to another user
    tg_row = await db.execute(
        text("SELECT user_id FROM telegram_identities WHERE telegram_chat_id = :chat_id"),
        {"chat_id": body.telegram_chat_id},
    )
    existing_tg = tg_row.fetchone()

    if existing_tg and str(existing_tg.user_id) != str(device_user_id):
        tg_owner_id = existing_tg.user_id
        await db.execute(
            text("UPDATE user_uuids SET user_id = :target WHERE uuid = :uuid"),
            {"target": str(tg_owner_id), "uuid": body.device_uuid},
        )
        await db.execute(
            text(
                "INSERT INTO user_merges (from_user_id, to_user_id, merge_reason) "
                "VALUES (:from_id, :to_id, 'telegram_link')"
            ),
            {"from_id": str(device_user_id), "to_id": str(tg_owner_id)},
        )
        target_user_id = tg_owner_id
        logger.info(
            "telegram_merge device_user=%s → tg_owner=%s chat_id=%d",
            device_user_id, tg_owner_id, body.telegram_chat_id,
        )
    else:
        target_user_id = device_user_id

    await db.execute(
        text(
            """
            INSERT INTO telegram_identities (
                user_id, telegram_chat_id, telegram_username,
                telegram_first_name, telegram_last_name, telegram_language_code,
                is_active, consecutive_errors
            ) VALUES (
                :user_id, :chat_id, :username,
                :first_name, :last_name, :lang_code,
                TRUE, 0
            )
            ON CONFLICT (telegram_chat_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                telegram_username = EXCLUDED.telegram_username,
                is_active = TRUE,
                consecutive_errors = 0,
                last_interaction_at = now()
            """
        ),
        {
            "user_id": str(target_user_id),
            "chat_id": body.telegram_chat_id,
            "username": body.telegram_username,
            "first_name": body.telegram_first_name,
            "last_name": body.telegram_last_name,
            "lang_code": body.telegram_language_code,
        },
    )
    await db.commit()
    return {"user_id": str(target_user_id)}


@router.post("/send-deal", status_code=200)
async def send_deal(
    body: SendDealRequest,
    db: AsyncSession = Depends(_get_session),
):
    """Send a saved deal to a Telegram chat and log the result."""
    # Verify identity is active
    tg_row = await db.execute(
        text(
            "SELECT is_active, telegram_username FROM telegram_identities "
            "WHERE telegram_chat_id = :chat_id"
        ),
        {"chat_id": body.telegram_chat_id},
    )
    tg_record = tg_row.fetchone()
    if tg_record is None:
        raise HTTPException(404, "Telegram identity not found")
    if not tg_record.is_active:
        raise HTTPException(403, "Telegram identity is deactivated")

    username_snapshot = tg_record.telegram_username
    status, error_text = await _send_telegram_message(
        body.telegram_chat_id, body.message_text
    )

    # Log the send attempt
    await db.execute(
        text(
            """
            INSERT INTO telegram_deal_sends (
                saved_deal_id, user_id, telegram_chat_id, telegram_username,
                message_text, status, error_text
            ) VALUES (
                :saved_deal_id, :user_id, :chat_id, :username,
                :message_text, :status, :error_text
            )
            """
        ),
        {
            "saved_deal_id": body.saved_deal_id,
            "user_id": body.user_id,
            "chat_id": body.telegram_chat_id,
            "username": username_snapshot,
            "message_text": body.message_text,
            "status": status,
            "error_text": error_text,
        },
    )

    if status in ("failed", "rate_limited"):
        await db.execute(
            text(
                "UPDATE telegram_identities "
                "SET consecutive_errors = consecutive_errors + 1 "
                "WHERE telegram_chat_id = :chat_id"
            ),
            {"chat_id": body.telegram_chat_id},
        )
        # Auto-deactivate after threshold
        await db.execute(
            text(
                "UPDATE telegram_identities SET is_active = FALSE "
                f"WHERE telegram_chat_id = :chat_id "
                f"AND consecutive_errors >= {_TG_CONSECUTIVE_ERROR_THRESHOLD}"
            ),
            {"chat_id": body.telegram_chat_id},
        )
        logger.warning(
            "telegram_send_%s chat_id=%d", status, body.telegram_chat_id
        )
    else:
        # Reset on success
        await db.execute(
            text(
                "UPDATE telegram_identities SET consecutive_errors = 0, "
                "last_interaction_at = now() WHERE telegram_chat_id = :chat_id"
            ),
            {"chat_id": body.telegram_chat_id},
        )

    await db.commit()
    return {"status": status, "chat_id": body.telegram_chat_id}


async def _send_telegram_message(chat_id: int, text_msg: str) -> tuple[str, str | None]:
    if not _BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — skipping actual send")
        return "sent", None
    url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text_msg})
        if resp.status_code == 200:
            return "sent", None
        if resp.status_code == 429:
            return "rate_limited", f"HTTP 429: {resp.text[:200]}"
        return "failed", f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return "failed", str(exc)[:200]
