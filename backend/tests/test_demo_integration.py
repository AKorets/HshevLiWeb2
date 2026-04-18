"""
Integration Tests — validates the live Python backend contract
that the Flutter frontend depends on.

Endpoints tested:
  GET  /rates/current   — exchange rates (requires X-API-Key)
  POST /rates/refresh   — manual rate refresh (requires X-API-Key)
  GET  /currencies      — currency whitelist (public)

Skipped automatically when LIVE_BACKEND_URL is not set, so they
do NOT interfere with the regular unit test suite.

Run locally:
    LIVE_BACKEND_URL=https://hashevli.co.il/backend \
    API_SECRET_KEY=<key> \
    pytest tests/test_demo_integration.py -v -m integration
"""

import os
import re
from datetime import datetime

import httpx
import pytest

# ── Configuration ────────────────────────────────────────────────────────────

LIVE_BACKEND_URL = os.environ.get("LIVE_BACKEND_URL", "").rstrip("/")
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "")

if not LIVE_BACKEND_URL:
    pytest.skip(
        "LIVE_BACKEND_URL not set — skipping integration tests.",
        allow_module_level=True,
    )

HEADERS = {"X-API-Key": API_SECRET_KEY} if API_SECRET_KEY else {}
TIMEOUT = 15  # seconds


# ── Helpers ──────────────────────────────────────────────────────────────────


def get(path: str, headers: dict | None = None) -> httpx.Response:
    h = headers if headers is not None else HEADERS
    with httpx.Client(timeout=TIMEOUT) as client:
        return client.get(f"{LIVE_BACKEND_URL}{path}", headers=h)


def post(path: str, headers: dict | None = None) -> httpx.Response:
    h = headers if headers is not None else HEADERS
    with httpx.Client(timeout=TIMEOUT) as client:
        return client.post(f"{LIVE_BACKEND_URL}{path}", headers=h)


# ── GET /currencies (public, no auth) ────────────────────────────────────────


@pytest.mark.integration
class TestCurrenciesEndpoint:
    """GET /currencies — the frontend calls this to populate the currency picker."""

    def test_returns_200(self) -> None:
        r = get("/currencies", headers={})
        assert r.status_code == 200, f"GET /currencies → {r.status_code}: {r.text}"

    def test_response_has_currencies_array(self) -> None:
        data = get("/currencies", headers={}).json()
        assert "currencies" in data, f"Missing 'currencies' key: {data}"
        assert isinstance(data["currencies"], list), f"currencies should be a list: {data}"

    def test_currencies_are_strings(self) -> None:
        codes = get("/currencies", headers={}).json()["currencies"]
        assert all(isinstance(c, str) for c in codes), f"All codes should be strings: {codes}"

    def test_ils_is_present(self) -> None:
        """ILS is the base currency and must always be in the list."""
        codes = get("/currencies", headers={}).json()["currencies"]
        assert "ILS" in codes, f"ILS missing from currencies: {codes}"

    def test_default_currencies_present(self) -> None:
        """Frontend fallback list must be a subset of backend response."""
        frontend_fallback = {"ILS", "USD", "EUR", "GBP", "RUB", "CHF", "PLN", "HUF", "JPY"}
        codes = set(get("/currencies", headers={}).json()["currencies"])
        missing = frontend_fallback - codes
        assert not missing, f"Frontend fallback currencies missing from backend: {missing}"

    def test_codes_are_iso4217_format(self) -> None:
        """All currency codes should be 3 uppercase letters."""
        codes = get("/currencies", headers={}).json()["currencies"]
        for code in codes:
            assert re.match(r"^[A-Z]{3}$", code), f"Invalid currency code format: {code}"


# ── GET /rates/current ───────────────────────────────────────────────────────


@pytest.mark.integration
class TestRatesCurrentEndpoint:
    """GET /rates/current — the frontend's primary data fetch.

    The Flutter RatesService parses these exact fields:
      ils_to_usdt  (num)
      usd_to_usdt  (num)
      euro_to_usdt (num)
      fetched_at   (ISO 8601 string, parsed via DateTime.parse)
      is_fresh     (bool)
    """

    def test_returns_200(self) -> None:
        r = get("/rates/current")
        assert r.status_code == 200, f"GET /rates/current → {r.status_code}: {r.text}"

    def test_required_fields_present(self) -> None:
        data = get("/rates/current").json()
        required = ("ils_to_usdt", "usd_to_usdt", "euro_to_usdt", "fetched_at", "is_fresh")
        missing = [f for f in required if f not in data]
        assert not missing, f"Missing fields in /rates/current: {missing}"

    def test_ils_to_usdt_is_positive_number(self) -> None:
        data = get("/rates/current").json()
        val = data["ils_to_usdt"]
        assert isinstance(val, (int, float)), f"ils_to_usdt should be numeric, got {type(val)}"
        assert val > 0, f"ils_to_usdt should be > 0, got {val}"

    def test_usd_to_usdt_is_one(self) -> None:
        """USD is pegged to USDT — frontend assumes this is always 1.0."""
        data = get("/rates/current").json()
        assert data["usd_to_usdt"] == 1.0, f"usd_to_usdt should be 1.0, got {data['usd_to_usdt']}"

    def test_euro_to_usdt_is_positive_number(self) -> None:
        data = get("/rates/current").json()
        val = data["euro_to_usdt"]
        assert isinstance(val, (int, float)), f"euro_to_usdt should be numeric, got {type(val)}"
        assert val > 0, f"euro_to_usdt should be > 0, got {val}"

    def test_fetched_at_is_parseable_datetime(self) -> None:
        """Frontend calls DateTime.parse() on this field — must be valid ISO 8601."""
        data = get("/rates/current").json()
        fetched_at = data["fetched_at"]
        assert fetched_at, "fetched_at should not be empty/null"
        try:
            datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        except (ValueError, TypeError) as e:
            pytest.fail(f"fetched_at '{fetched_at}' is not valid ISO 8601: {e}")

    def test_is_fresh_is_boolean(self) -> None:
        data = get("/rates/current").json()
        assert isinstance(data["is_fresh"], bool), (
            f"is_fresh should be boolean, got {type(data['is_fresh'])}"
        )

    def test_rates_map_present_when_returned(self) -> None:
        """The 'rates' field (optional) maps currency codes to rate values."""
        data = get("/rates/current").json()
        if "rates" in data and data["rates"] is not None:
            rates = data["rates"]
            assert isinstance(rates, dict), f"rates should be an object, got {type(rates)}"
            for code, val in rates.items():
                assert re.match(r"^[A-Z]{3,4}$", code), f"Invalid rate key: {code}"
                assert isinstance(val, (int, float)) and val > 0, (
                    f"Rate for {code} should be positive number, got {val}"
                )

    def test_rate_values_are_reasonable(self) -> None:
        """Sanity check: rates should be within plausible real-world ranges."""
        data = get("/rates/current").json()
        ils = data["ils_to_usdt"]
        eur = data["euro_to_usdt"]
        # ILS/USD historically between 2.5 and 5.0
        assert 2.0 < ils < 6.0, f"ils_to_usdt={ils} seems unreasonable"
        # EUR/USD historically between 0.7 and 1.5
        assert 0.5 < eur < 2.0, f"euro_to_usdt={eur} seems unreasonable"


# ── Authentication ───────────────────────────────────────────────────────────


@pytest.mark.integration
class TestAuthentication:
    """Protected endpoints must reject invalid/missing API keys."""

    def test_rates_without_key_returns_401(self) -> None:
        r = get("/rates/current", headers={})
        assert r.status_code == 401, (
            f"GET /rates/current without key should return 401, got {r.status_code}"
        )

    def test_rates_with_bad_key_returns_401(self) -> None:
        r = get("/rates/current", headers={"X-API-Key": "invalid-key-12345"})
        assert r.status_code == 401, (
            f"GET /rates/current with bad key should return 401, got {r.status_code}"
        )

    def test_refresh_without_key_returns_401(self) -> None:
        r = post("/rates/refresh", headers={})
        assert r.status_code == 401, (
            f"POST /rates/refresh without key should return 401, got {r.status_code}"
        )

    def test_currencies_is_public(self) -> None:
        """GET /currencies should NOT require authentication."""
        r = get("/currencies", headers={})
        assert r.status_code == 200, (
            f"GET /currencies should be public (200), got {r.status_code}"
        )


# ── POST /rates/refresh ─────────────────────────────────────────────────────


@pytest.mark.integration
class TestRatesRefreshEndpoint:
    """POST /rates/refresh — manual rate refresh with 60-second guard."""

    def test_returns_200(self) -> None:
        r = post("/rates/refresh")
        assert r.status_code == 200, f"POST /rates/refresh → {r.status_code}: {r.text}"

    def test_required_fields_present(self) -> None:
        data = post("/rates/refresh").json()
        required = (
            "ils_to_usdt", "usd_to_usdt", "euro_to_usdt",
            "fetched_at", "is_fresh", "refreshed",
        )
        missing = [f for f in required if f not in data]
        assert not missing, f"Missing fields in /rates/refresh: {missing}"

    def test_refreshed_is_boolean(self) -> None:
        data = post("/rates/refresh").json()
        assert isinstance(data["refreshed"], bool), (
            f"'refreshed' should be boolean, got {type(data['refreshed'])}"
        )

    def test_60sec_guard_returns_too_soon(self) -> None:
        """Two rapid calls: second should be blocked with reason='too_soon'."""
        first = post("/rates/refresh").json()
        if first.get("refreshed") is True:
            second = post("/rates/refresh").json()
            assert second["refreshed"] is False, "Second immediate refresh should be blocked"
            assert second.get("reason") == "too_soon", (
                f"Expected reason='too_soon', got: {second.get('reason')}"
            )


# ── CORS ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestCORS:
    """Flutter web app needs proper CORS headers from the backend."""

    def test_cors_headers_present(self) -> None:
        r = get("/currencies", headers={"Origin": "https://hashevli.co.il"})
        cors_header = r.headers.get("access-control-allow-origin", "")
        assert cors_header, "Access-Control-Allow-Origin header is missing"

    def test_options_preflight(self) -> None:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.options(
                f"{LIVE_BACKEND_URL}/rates/current",
                headers={
                    "Origin": "https://hashevli.co.il",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "X-API-Key",
                },
            )
        assert r.status_code in (200, 204), f"OPTIONS preflight → {r.status_code}"
        assert "access-control-allow-methods" in r.headers, "Missing Allow-Methods header"
