import asyncio
import logging
from datetime import datetime, timezone

from . import app_settings
from .models import RateSnapshot
from .xe_service import fetch_rates_from_fallback, fetch_rates_from_xe

logger = logging.getLogger(__name__)

CACHE_FRESH_SECONDS = 300   # freshness window for lazy-refresh
REFRESH_GUARD_SECONDS = 60  # minimum interval for manual refresh


class RatesCache:
    def __init__(self) -> None:
        self.ils_to_usdt: float = 0.0
        self.usd_to_usdt: float = 1.0
        self.euro_to_usdt: float = 0.0
        self.rates: dict[str, float] = {}
        self.fetched_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self.last_fetch_error: str | None = None
        self.snapshot_id: int | None = None
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
            "snapshot_id": self.snapshot_id,
        }

    async def _do_fetch_locked(self) -> bool:
        """Perform the actual fetch + persist. Must be called with _lock held."""
        use_fallback = await app_settings.get_bool("rates_fallback", default=True)
        if use_fallback:
            rates, error = await fetch_rates_from_fallback()
        else:
            rates, error = await fetch_rates_from_xe(refresh_interval_seconds=CACHE_FRESH_SECONDS)
        if rates is None:
            self.last_fetch_error = error
            logger.error("Cache refresh failed: %s", error)
            return False

        self.ils_to_usdt = rates["ils_to_usdt"]
        self.usd_to_usdt = rates["usd_to_usdt"]
        self.euro_to_usdt = rates["euro_to_usdt"]
        self.rates = rates.get("rates", {})
        self.fetched_at = datetime.now(timezone.utc)
        self.last_fetch_error = None

        await self._persist()
        logger.info("Cache refreshed at %s", self.fetched_at.isoformat())
        return True

    async def fetch(self) -> bool:
        """Force a fetch regardless of freshness. Returns True on success."""
        async with self._lock:
            return await self._do_fetch_locked()

    async def ensure_fresh(self) -> None:
        """Fetch only if the cache is stale. Safe under concurrent requests."""
        if self.is_fresh:
            return
        async with self._lock:
            if self.is_fresh:  # another waiter may have refreshed while we blocked
                return
            await self._do_fetch_locked()

    async def _persist(self) -> None:
        """Write snapshot to PostgreSQL (best-effort — DB failure doesn't break in-memory cache)."""
        try:
            from .database import get_session_factory
            session_factory = get_session_factory()
            async with session_factory() as session:
                snapshot = RateSnapshot(
                    ils_to_usdt=self.ils_to_usdt,
                    usd_to_usdt=self.usd_to_usdt,
                    euro_to_usdt=self.euro_to_usdt,
                    fetched_at=self.fetched_at,
                )
                session.add(snapshot)
                await session.flush()
                self.snapshot_id = snapshot.id
                await session.commit()
        except Exception:
            pass

    async def try_manual_refresh(self) -> dict:
        """Attempt a manual refresh. Enforces the 60-second guard."""
        if self.seconds_since_fetch < REFRESH_GUARD_SECONDS:
            logger.info(
                "Manual refresh blocked: last fetch was %.1fs ago (guard=%ds)",
                self.seconds_since_fetch,
                REFRESH_GUARD_SECONDS,
            )
            return {**self.snapshot(), "refreshed": False, "reason": "too_soon"}
        logger.info("Manual refresh triggered")
        success = await self.fetch()
        return {**self.snapshot(), "refreshed": success}


_cache = RatesCache()


def get_cache() -> RatesCache:
    return _cache
