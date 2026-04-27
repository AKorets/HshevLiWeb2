"""POST /sessions/heartbeat — upsert session from request headers."""

from __future__ import annotations
import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, Header, Request, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session_factory
from ..services.ip_hash import hash_ip
from ..services.geo_lookup import lookup as geo_lookup
from ..services.device_context import DeviceContext
from ..services.session_stitcher import find_stitchable_session, stitch_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])

_GA_HEADERS_REQUIRED = os.environ.get("GA_HEADERS_REQUIRED", "true").lower() == "true"


class HeartbeatRequest(BaseModel):
    user_uuid: str
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    referrer: str | None = None
    locale: str | None = None
    user_agent: str | None = None
    device_context: DeviceContext | None = None
    experiment_flags: dict | None = None
    # Session quality metrics (Phase 11)
    scroll_depth_percent: int | None = None
    time_to_first_action_ms: int | None = None
    hesitation_before_calc_ms: int | None = None
    # Client-reported environment — more reliable than host-header sniffing
    # through DO App Platform's internal proxy which rewrites Host.
    environment: str | None = None


async def _get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


def _require_ga_header(value: str | None, name: str) -> str:
    if not value:
        if _GA_HEADERS_REQUIRED:
            raise HTTPException(
                status_code=400,
                detail=f"Required header {name} is missing. "
                       "Set GA_HEADERS_REQUIRED=false for rollout mode.",
            )
        return ""
    return value


@router.post("/heartbeat", status_code=200)
async def heartbeat(
    body: HeartbeatRequest,
    request: Request,
    x_ga_client_id: str | None = Header(None, alias="X-GA-Client-Id"),
    x_ga_session_id: str | None = Header(None, alias="X-GA-Session-Id"),
    x_tab_id: str | None = Header(None, alias="X-Tab-Id"),
    db: AsyncSession = Depends(_get_session),
):
    ga_client_id = _require_ga_header(x_ga_client_id, "X-GA-Client-Id")
    ga_session_id = _require_ga_header(x_ga_session_id, "X-GA-Session-Id")

    environment = body.environment or _detect_environment(request)
    client_ip = _get_client_ip(request)
    ip_hash_bytes = hash_ip(client_ip) if client_ip else None
    geo = geo_lookup(client_ip) if client_ip else None

    # Ensure user and user_uuid rows exist
    user_uuid_obj = uuid.UUID(body.user_uuid)
    result = await db.execute(
        text("SELECT user_id FROM user_uuids WHERE uuid = :uuid"),
        {"uuid": str(user_uuid_obj)},
    )
    row = result.fetchone()

    if row is None:
        user_id = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO users (id, kind) VALUES (:id, 'anonymous') "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": str(user_id)},
        )
        await db.execute(
            text(
                "INSERT INTO user_uuids (uuid, user_id) VALUES (:uuid, :user_id) "
                "ON CONFLICT DO NOTHING"
            ),
            {"uuid": str(user_uuid_obj), "user_id": str(user_id)},
        )
    else:
        user_id = row.user_id
        await db.execute(
            text("UPDATE user_uuids SET last_seen_at = now() WHERE uuid = :uuid"),
            {"uuid": str(user_uuid_obj)},
        )

    # Session stitching: check if GA4 midnight boundary split a session
    stitchable = await find_stitchable_session(db, ga_client_id, environment)
    if stitchable and ga_session_id:
        await stitch_session(db, stitchable, ga_session_id)
        # Update quality metrics on the stitched session
        if any([body.scroll_depth_percent, body.time_to_first_action_ms, body.hesitation_before_calc_ms]):
            await db.execute(
                text(
                    "UPDATE sessions SET "
                    "scroll_depth_percent = GREATEST(COALESCE(scroll_depth_percent, 0), :sdp), "
                    "time_to_first_action_ms = COALESCE(time_to_first_action_ms, :ttfa), "
                    "hesitation_before_calc_ms = COALESCE(hesitation_before_calc_ms, :hbc) "
                    "WHERE id = :id"
                ),
                {
                    "sdp": body.scroll_depth_percent or 0,
                    "ttfa": body.time_to_first_action_ms,
                    "hbc": body.hesitation_before_calc_ms,
                    "id": stitchable,
                },
            )
        await db.commit()
        return {"session_id": stitchable, "user_id": str(user_id), "stitched": True}

    # Upsert session
    dc = body.device_context
    session_result = await db.execute(
        text(
            """
            INSERT INTO sessions (
                user_id, user_uuid, ga_client_id, ga_session_id, environment,
                locale, user_agent, referrer,
                utm_source, utm_medium, utm_campaign, ip_hash,
                device_type, os_family, browser_family,
                screen_width, screen_height, viewport_width, viewport_height,
                device_pixel_ratio, cpu_cores, device_memory_gb,
                country_code, city, isp, connection_type, experiment_flags,
                scroll_depth_percent, time_to_first_action_ms, hesitation_before_calc_ms,
                first_seen_at, last_seen_at
            ) VALUES (
                :user_id, :user_uuid, :ga_client_id, :ga_session_id, :environment,
                :locale, :user_agent, :referrer,
                :utm_source, :utm_medium, :utm_campaign, :ip_hash,
                :device_type, :os_family, :browser_family,
                :screen_width, :screen_height, :viewport_width, :viewport_height,
                :device_pixel_ratio, :cpu_cores, :device_memory_gb,
                :country_code, :city, :isp, :connection_type, CAST(:experiment_flags AS JSONB),
                :scroll_depth_percent, :time_to_first_action_ms, :hesitation_before_calc_ms,
                now(), now()
            )
            ON CONFLICT (ga_client_id, ga_session_id, environment)
            DO UPDATE SET
                last_seen_at = now(),
                device_type = COALESCE(EXCLUDED.device_type, sessions.device_type),
                connection_type = COALESCE(EXCLUDED.connection_type, sessions.connection_type),
                experiment_flags = COALESCE(EXCLUDED.experiment_flags, sessions.experiment_flags),
                scroll_depth_percent = GREATEST(
                    COALESCE(sessions.scroll_depth_percent, 0),
                    COALESCE(EXCLUDED.scroll_depth_percent, 0)
                )
            RETURNING id
            """
        ),
        {
            "user_id": str(user_id),
            "user_uuid": str(user_uuid_obj),
            "ga_client_id": ga_client_id,
            "ga_session_id": ga_session_id,
            "environment": environment,
            "locale": body.locale,
            "user_agent": body.user_agent,
            "referrer": body.referrer,
            "utm_source": body.utm_source,
            "utm_medium": body.utm_medium,
            "utm_campaign": body.utm_campaign,
            "ip_hash": ip_hash_bytes,
            "device_type": dc.device_type if dc else None,
            "os_family": dc.os_family if dc else None,
            "browser_family": dc.browser_family if dc else None,
            "screen_width": dc.screen_width if dc else None,
            "screen_height": dc.screen_height if dc else None,
            "viewport_width": dc.viewport_width if dc else None,
            "viewport_height": dc.viewport_height if dc else None,
            "device_pixel_ratio": float(dc.device_pixel_ratio) if dc and dc.device_pixel_ratio else None,
            "cpu_cores": dc.cpu_cores if dc else None,
            "device_memory_gb": float(dc.device_memory_gb) if dc and dc.device_memory_gb else None,
            "country_code": geo.country_code if geo else None,
            "city": geo.city if geo else None,
            "isp": geo.isp if geo else None,
            "connection_type": dc.connection_type if dc else None,
            # asyncpg requires JSONB to be JSON-encoded; CAST in SQL above.
            "experiment_flags": (
                json.dumps(body.experiment_flags)
                if body.experiment_flags is not None else None
            ),
            "scroll_depth_percent": body.scroll_depth_percent,
            "time_to_first_action_ms": body.time_to_first_action_ms,
            "hesitation_before_calc_ms": body.hesitation_before_calc_ms,
        },
    )
    session_id = session_result.scalar_one()
    await db.commit()

    return {"session_id": str(session_id), "user_id": str(user_id), "stitched": False}


def _detect_environment(request: Request) -> str:
    # DO App Platform rewrites the Host header to the internal service hostname
    # (contains "ondigitalocean"), so check X-Forwarded-Host first — that
    # carries the browser-visible domain (e.g. hashevli.co.il).
    host = (
        request.headers.get("X-Forwarded-Host")
        or request.headers.get("host", "")
    )
    if "demo" in host:
        return "demo"
    if "staging" in host or "ondigitalocean" in host:
        return "staging"
    return "prod"


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", None)
