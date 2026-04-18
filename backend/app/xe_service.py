import httpx
from .config import settings

XE_API_URL = "https://xecdapi.xe.com/v1/convert_from.json"
CURRENCIES = ["ILS", "USD", "EUR", "GBP", "RUB", "CHF", "PLN", "HUF", "JPY"]


async def fetch_rates_from_xe() -> tuple[dict | None, str | None]:
    """Fetch current rates from XE API.

    Returns (rates_dict, error_message). On success error_message is None.
    On failure rates_dict is None and error_message describes what went wrong.
    """
    if not settings.xe_account_id or not settings.xe_api_key:
        return None, "XE credentials not configured (XE_ACCOUNT_ID or XE_API_KEY is empty)"

    try:
        to_currencies = ",".join(c for c in CURRENCIES if c != "USD")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                XE_API_URL,
                params={"from": "USD", "to": to_currencies, "amount": 1},
                auth=(settings.xe_account_id, settings.xe_api_key),
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

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
        return result, None
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300]
        return None, f"XE API HTTP {exc.response.status_code}: {body}"
    except Exception as exc:
        return None, f"XE API error: {type(exc).__name__}: {exc}"
