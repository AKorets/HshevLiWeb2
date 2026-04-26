"""POST /auth/link-identity — OAuth identity linking and anon→OAuth merge."""

from __future__ import annotations
import logging
import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_factory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LinkIdentityRequest(BaseModel):
    provider: str  # 'google' or 'apple'
    provider_subject: str
    device_uuid: str
    email: str | None = None


async def _get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


@router.post("/link-identity", status_code=200)
async def link_identity(
    body: LinkIdentityRequest,
    db: AsyncSession = Depends(_get_session),
):
    """Link an OAuth identity to the user identified by device_uuid.

    Merge flow:
    1. Resolve device_uuid → anon_user_id
    2. Check if (provider, provider_subject) already exists
    3a. If existing OAuth user: reassign user_uuids row, log user_merges, soft-retire anon
    3b. If no existing OAuth user: upgrade anon user in place (kind→oauth, insert oauth_identities)
    """
    if body.provider not in ("google", "apple"):
        raise HTTPException(400, "provider must be 'google' or 'apple'")

    # 1. Resolve device_uuid → anon user
    uuid_row = await db.execute(
        text("SELECT user_id FROM user_uuids WHERE uuid = :uuid"),
        {"uuid": body.device_uuid},
    )
    uuid_record = uuid_row.fetchone()
    if uuid_record is None:
        raise HTTPException(404, "device_uuid not found")
    anon_user_id = uuid_record.user_id

    # 2. Check existing OAuth identity
    oauth_row = await db.execute(
        text(
            "SELECT user_id FROM oauth_identities "
            "WHERE provider = :provider AND provider_subject = :subject"
        ),
        {"provider": body.provider, "subject": body.provider_subject},
    )
    existing_oauth = oauth_row.fetchone()

    if existing_oauth:
        # 3a. Existing OAuth user — reassign device UUID, log merge, soft-retire anon
        target_user_id = existing_oauth.user_id
        if str(target_user_id) != str(anon_user_id):
            await db.execute(
                text("UPDATE user_uuids SET user_id = :target WHERE uuid = :uuid"),
                {"target": str(target_user_id), "uuid": body.device_uuid},
            )
            await db.execute(
                text(
                    "INSERT INTO user_merges (from_user_id, to_user_id, merge_reason) "
                    "VALUES (:from_id, :to_id, 'oauth_link')"
                ),
                {"from_id": str(anon_user_id), "to_id": str(target_user_id)},
            )
            await db.execute(
                text("UPDATE users SET deleted_at = now(), kind = 'deleted' WHERE id = :id"),
                {"id": str(anon_user_id)},
            )
            logger.info(
                "user_merge anon=%s → oauth_user=%s provider=%s",
                anon_user_id, target_user_id, body.provider,
            )
        merged = True
        user_id = target_user_id
    else:
        # 3b. Upgrade anon user in place
        user_id = anon_user_id
        await db.execute(
            text("UPDATE users SET kind = 'oauth' WHERE id = :id AND kind = 'anonymous'"),
            {"id": str(user_id)},
        )

        # Check consent_pii before storing email
        consent_row = await db.execute(
            text("SELECT consent_pii FROM users WHERE id = :id"),
            {"id": str(user_id)},
        )
        consent = consent_row.scalar_one_or_none()
        email_to_store = body.email if consent else None

        await db.execute(
            text(
                "INSERT INTO oauth_identities (user_id, provider, provider_subject, email) "
                "VALUES (:user_id, :provider, :subject, :email) "
                "ON CONFLICT (provider, provider_subject) DO NOTHING"
            ),
            {
                "user_id": str(user_id),
                "provider": body.provider,
                "subject": body.provider_subject,
                "email": email_to_store,
            },
        )
        merged = False

    await db.commit()
    return {"user_id": str(user_id), "merged": merged}
