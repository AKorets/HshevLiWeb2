import asyncio
from datetime import datetime, timezone

from .models import RateSnapshot
from .xe_service import fetch_rates_from_xe

CACHE_FRESH_SECONDS = 300   # auto-refresh every 5 minutes
REFRESH_GUARD_SECONDS = 60  # minimum interval for manual refresh


class RatesCache:
    def __init__(self) -> None:
        self.ils_to_usdt: float = 0.0
        self.usd_to_usdt: float = 1.0
        self.euro_to_usdt: float = 0.0
        self.rates: dict[str, float] = {}
        self.fetched_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self.last_fetch_error: str | None = None
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
            "rates": self.rates if self.rates else None,
            "fetched_at": self.fetched_at,
            "is_fresh": self.is_fresh,
            "last_fetch_error": self.last_fetch_error,
        }

    async def fetch(self) -> bool:
        """Fetch from XE API, update in-memory cache, and persist to DB. Returns True on success."""
        async with self._lock:
            rates, error = await fetch_rates_from_xe()
            if rates is None:
                self.last_fetch_error = error
                return False

            self.ils_to_usdt = rates["ils_to_usdt"]
            self.usd_to_usdt = rates["usd_to_usdt"]
            self.euro_to_usdt = rates["euro_to_usdt"]
            self.rates = rates.get("rates", {})
            self.fetched_at = datetime.now(timezone.utc)
            self.last_fetch_error = None

            await self._persist()
            return True

    async def _persist(self) -> None:
        """Write snapshot to PostgreSQL (best-effort — DB failure doesn't break in-memory cache)."""
        try:
            from .database import get_session_factory
            session_factory = get_session_factory()
            async with session_factory() as session:
                session.add(RateSnapshot(
                    ils_to_usdt=self.ils_to_usdt,
                    usd_to_usdt=self.usd_to_usdt,
                    euro_to_usdt=self.euro_to_usdt,
                    fetched_at=self.fetched_at,
                ))
                await session.commit()
        except Exception:
            pass

    async def try_manual_refresh(self) -> dict:
        """Attempt a manual refresh. Enforces the 60-second guard."""
        if self.seconds_since_fetch < REFRESH_GUARD_SECONDS:
            return {**self.snapshot(), "refreshed": False, "reason": "too_soon"}
        success = await self.fetch()
        return {**self.snapshot(), "refreshed": success}


_cache = RatesCache()


def get_cache() -> RatesCache:
    return _cache


async def background_refresh_loop() -> None:
    """Auto-refresh rates every 5 minutes in the background."""
    while True:
        await _cache.fetch()
        await asyncio.sleep(CACHE_FRESH_SECONDS)
