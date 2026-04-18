from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services.xe_service import get_cache

router = APIRouter(prefix="/rates", tags=["rates"])


class RatesResponse(BaseModel):
    ils_to_usdt: float
    usd_to_usdt: float
    euro_to_usdt: float
    fetched_at: datetime
    is_fresh: bool
    is_fallback: bool


class RefreshResponse(RatesResponse):
    refreshed: bool
    reason: Optional[str] = None


@router.get("/current", response_model=RatesResponse)
async def get_current_rates() -> RatesResponse:
    cache = get_cache()
    snap = cache.snapshot()
    return RatesResponse(**snap)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_rates() -> RefreshResponse:
    cache = get_cache()
    result = await cache.try_manual_refresh()
    return RefreshResponse(**result)
