from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.xe_service import CACHE_FRESH_SECONDS, RatesCache


@pytest.fixture
def cache() -> RatesCache:
    return RatesCache()


def _mock_xe_client() -> AsyncMock:
    """Return a patched httpx.AsyncClient context manager with a fake XE response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "to": [
            {"quotecurrency": "ILS", "mid": 3.71},
            {"quotecurrency": "EUR", "mid": 1.08},
        ]
    }

    client = AsyncMock()
    client.get.return_value = resp
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False

    client_cls = MagicMock()
    client_cls.return_value = client
    return client_cls


@pytest.mark.asyncio
async def test_60sec_guard_returns_same_fetched_at(cache: RatesCache) -> None:
    """Two consecutive calls within 60 sec return identical fetched_at."""
    with patch("services.xe_service.httpx.AsyncClient", _mock_xe_client()):
        result1 = await cache.try_manual_refresh()
        assert result1["refreshed"] is True

        result2 = await cache.try_manual_refresh()
        assert result2["refreshed"] is False
        assert result2["reason"] == "too_soon"
        assert result1["fetched_at"] == result2["fetched_at"]


@pytest.mark.asyncio
async def test_is_fresh_flips_after_5min(cache: RatesCache) -> None:
    """After 5 minutes, is_fresh flips to False."""
    with patch("services.xe_service.httpx.AsyncClient", _mock_xe_client()):
        await cache.fetch_from_xe()
        assert cache.is_fresh is True

    cache.fetched_at = datetime.now(timezone.utc) - timedelta(
        seconds=CACHE_FRESH_SECONDS + 1
    )
    assert cache.is_fresh is False


@pytest.mark.asyncio
async def test_fetch_populates_rates(cache: RatesCache) -> None:
    """Successful fetch populates ILS and EUR rates."""
    with patch("services.xe_service.httpx.AsyncClient", _mock_xe_client()):
        success = await cache.fetch_from_xe()

    assert success is True
    assert cache.ils_to_usdt == 3.71
    assert cache.euro_to_usdt == 1.08
    assert cache.usd_to_usdt == 1.0


@pytest.mark.asyncio
async def test_fetch_failure_returns_false(cache: RatesCache) -> None:
    """Network failure returns False without crashing."""
    client = AsyncMock()
    client.get.side_effect = Exception("network error")
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False

    client_cls = MagicMock(return_value=client)

    with patch("services.xe_service.httpx.AsyncClient", client_cls):
        success = await cache.fetch_from_xe()

    assert success is False
