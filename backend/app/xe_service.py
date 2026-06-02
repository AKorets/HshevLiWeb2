import logging
from datetime import datetime, timedelta, timezone
import httpx
from .config import settings

logger = logging.getLogger(__name__)

XE_API_URL = "https://xecdapi.xe.com/v1/convert_from.json"
XE_ACCOUNT_INFO_URL = "https://xecdapi.xe.com/v1/account_info.json"
FALLBACK_API_URL = "https://open.er-api.com/v6/latest/USD"
CURRENCIES = ["ILS", "USD", "EUR", "GBP", "RUB", "CHF", "PLN", "HUF", "JPY"]


async def fetch_rates_from_fallback() -> tuple[dict | None, str | None]:
    """Fetch rates from open.er-api.com (free fallback, no auth required)."""
    logger.info("Fallback call: fetching rates from %s", FALLBACK_API_URL)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(FALLBACK_API_URL, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()

        raw = data.get("rates", {})
        rates_map: dict[str, float] = {"USD": 1.0, "USDT": 1.0}
        for code in CURRENCIES:
            if code != "USD" and code in raw:
                rates_map[code] = float(raw[code])

        result: dict = {
            "usd_to_usdt": 1.0,
            "ils_to_usdt": rates_map.get("ILS", 0.0),
            "euro_to_usdt": rates_map.get("EUR", 0.0),
            "rates": rates_map,
        }
        logger.info(
            "Fallback call success: ils_to_usdt=%.4f euro_to_usdt=%.4f",
            result["ils_to_usdt"],
            result["euro_to_usdt"],
        )
        return result, None
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300]
        error = f"Fallback API HTTP {exc.response.status_code}: {body}"
        logger.error("Fallback call failed: %s", error)
        return None, error
    except Exception as exc:
        error = f"Fallback API error: {type(exc).__name__}: {exc}"
        logger.error("Fallback call failed: %s", error)
        return None, error


async def fetch_rates_from_xe(refresh_interval_seconds: int = 300) -> tuple[dict | None, str | None]:
    """Fetch current rates from XE API.

    Returns (rates_dict, error_message). On success error_message is None.
    On failure rates_dict is None and error_message describes what went wrong.
    """
    if not settings.xe_account_id or not settings.xe_api_key:
        error = "XE credentials not configured (XE_ACCOUNT_ID or XE_API_KEY is empty)"
        logger.error("XE call skipped: %s", error)
        return None, error

    logger.info("XE call: fetching rates from %s", XE_API_URL)
    try:
        to_currencies = ",".join(c for c in CURRENCIES if c != "USD")
        calls_this_fetch = len(to_currencies.split(","))

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                XE_API_URL,
                params={"from": "USD", "to": to_currencies, "amount": 1},
                auth=(settings.xe_account_id, settings.xe_api_key),
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

            # account_info.json is quota-free — confirmed: two consecutive calls
            # leave package_limit_remaining unchanged.
            acct_data: dict | None = None
            try:
                acct_resp = await client.get(
                    XE_ACCOUNT_INFO_URL,
                    auth=(settings.xe_account_id, settings.xe_api_key),
                    timeout=10.0,
                )
                if acct_resp.status_code == 200:
                    acct_data = acct_resp.json()
            except Exception:
                pass

        rates_map: dict[str, float] = {"USD": 1.0, "USDT": 1.0}
        result: dict = {"usd_to_usdt": 1.0, "ils_to_usdt": 0.0, "euro_to_usdt": 0.0}
        for item in data.get("to", []):
            code = item.get("quotecurrency", "")
            mid = float(item.get("mid", 0))
            rates_map[code] = mid
            if code == "ILS":
                result["ils_to_usdt"] = mid
            elif code == "EUR":
                result["euro_to_usdt"] = mid
        result["rates"] = rates_map

        logger.info(
            "XE call success: ils_to_usdt=%.4f euro_to_usdt=%.4f",
            result["ils_to_usdt"],
            result["euro_to_usdt"],
        )
        if acct_data:
            _log_xe_quota(acct_data, calls_this_fetch, refresh_interval_seconds)

        return result, None
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300]
        error = f"XE API HTTP {exc.response.status_code}: {body}"
        logger.error("XE call failed: %s", error)
        return None, error
    except Exception as exc:
        error = f"XE API error: {type(exc).__name__}: {exc}"
        logger.error("XE call failed: %s", error)
        return None, error


def _log_xe_quota(acct: dict, calls_this_fetch: int, refresh_interval_seconds: int) -> None:
    try:
        remaining: int = acct["package_limit_remaining"]
        limit: int     = acct["package_limit"]
        reset_str: str = acct["package_limit_reset"]
        reset_dt       = datetime.fromisoformat(reset_str.replace("Z", "+00:00"))

        now          = datetime.now(timezone.utc)
        refreshes_left = remaining / calls_this_fetch
        depletes_at  = now + timedelta(seconds=refreshes_left * refresh_interval_seconds)

        if depletes_at < reset_dt:
            days_early = (reset_dt - depletes_at).days
            verdict = f"EXHAUSTED {days_early}d before reset"
        else:
            days_after = (depletes_at - reset_dt).days
            verdict = f"ok (outlasts reset by {days_after}d)"

        logger.info(
            "XE quota: consumed=%d remaining=%d/%d | depletes=%s reset=%s [%s]",
            calls_this_fetch,
            remaining,
            limit,
            depletes_at.strftime("%Y-%m-%dT%H:%MZ"),
            reset_dt.strftime("%Y-%m-%dT%H:%MZ"),
            verdict,
        )
    except Exception as exc:
        logger.warning("XE quota log failed: %s", exc)
