import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env")

XE_ACCOUNT_ID = os.getenv("XE_ACCOUNT_ID", "")
XE_API_KEY = os.getenv("XE_API_KEY", "")
XE_API_URL = "https://xecdapi.xe.com/v1/convert_from.json"
FALLBACK_API_URL = "https://open.er-api.com/v6/latest/USD"

# If RATES_FALLBACK env var exists (any value), use the fallback API instead of XE.
RATES_FALLBACK = os.getenv("RATES_FALLBACK") is not None

CACHE_FRESH_SECONDS = 300  # 5 minutes
REFRESH_GUARD_SECONDS = 60  # 60-second manual refresh guard


class RatesCache:
    def __init__(self) -> None:
        self.ils_to_usdt: float = 0.0
        self.usd_to_usdt: float = 1.0
        self.euro_to_usdt: float = 0.0
        self.fetched_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self.is_fallback: bool = RATES_FALLBACK
        self._lock = asyncio.Lock()

    @property
    def is_fresh(self) -> bool:
        age = (datetime.now(timezone.utc) - self.fetched_at).total_seconds()
        return age < CACHE_FRESH_SECONDS

    @property
    def seconds_since_fetch(self) -> float:
        return (datetime.now(timezone.utc) - self.fetched_at).total_seconds()

    def snapshot(self) -> dict:
        return {
            "ils_to_usdt": self.ils_to_usdt,
            "usd_to_usdt": self.usd_to_usdt,
            "euro_to_usdt": self.euro_to_usdt,
            "fetched_at": self.fetched_at,
            "is_fresh": self.is_fresh,
            "is_fallback": self.is_fallback,
        }

    async def fetch_from_xe(self) -> bool:
        """Fetch rates from XE API. Returns True on success."""
        async with self._lock:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        XE_API_URL,
                        params={"from": "USD", "to": "ILS,EUR", "amount": 1},
                        auth=(XE_ACCOUNT_ID, XE_API_KEY),
                        timeout=10.0,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                for item in data.get("to", []):
                    code = item.get("quotecurrency", "")
                    mid = float(item.get("mid", 0))
                    if code == "ILS":
                        self.ils_to_usdt = mid
                    elif code == "EUR":
                        self.euro_to_usdt = mid

                self.usd_to_usdt = 1.0
                self.fetched_at = datetime.now(timezone.utc)
                self.is_fallback = False
                return True
            except Exception:
                return False

    async def fetch_from_fallback(self) -> bool:
        """Fetch rates from open.er-api.com. Returns True on success."""
        async with self._lock:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(FALLBACK_API_URL, timeout=10.0)
                    resp.raise_for_status()
                    data = resp.json()

                rates = data.get("rates", {})
                self.ils_to_usdt = float(rates.get("ILS", self.ils_to_usdt))
                self.euro_to_usdt = float(rates.get("EUR", self.euro_to_usdt))
                self.usd_to_usdt = 1.0
                self.fetched_at = datetime.now(timezone.utc)
                self.is_fallback = True
                return True
            except Exception:
                return False

    async def _fetch(self) -> bool:
        """Fetch rates from the configured source."""
        if RATES_FALLBACK:
            return await self.fetch_from_fallback()
        return await self.fetch_from_xe()

    async def try_manual_refresh(self) -> dict:
        """Attempt a manual refresh. Enforces 60-sec guard."""
        if self.seconds_since_fetch < REFRESH_GUARD_SECONDS:
            return {**self.snapshot(), "refreshed": False, "reason": "too_soon"}

        success = await self._fetch()
        return {**self.snapshot(), "refreshed": success}


_cache = RatesCache()


def get_cache() -> RatesCache:
    return _cache


async def background_refresh_loop() -> None:
    """Auto-refresh rates every 5 minutes."""
    while True:
        await _cache._fetch()
        await asyncio.sleep(CACHE_FRESH_SECONDS)
