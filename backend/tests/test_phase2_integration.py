"""
Phase 2 Integration Tests — Live DO App Platform Validation.

Validates:
  1. All API endpoints respond correctly against the deployed app.
  2. Rate snapshots are persisted to the PostgreSQL rate_snapshots table.

These tests are skipped automatically when APP_URL is not set, so they
do NOT interfere with the regular backend test suite.

Run via the 'Phase 2 Integration Tests' GitHub Actions workflow (manual trigger),
or locally with:
    APP_URL=https://your-app.ondigitalocean.app \\
    DATABASE_URL=postgresql://user:pass@host:port/db \\
    pytest tests/test_phase2_integration.py -v -m integration
"""

import asyncio
import os
import time

import httpx
import pytest

# ── Configuration ────────────────────────────────────────────────────────────

APP_URL = os.environ.get("APP_URL", "").rstrip("/")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "")

# Skip the entire module when APP_URL is absent (regular CI runs)
if not APP_URL:
    pytest.skip(
        "APP_URL not set — skipping Phase 2 integration tests. "
        "Set APP_URL to the deployed app base URL to run these tests.",
        allow_module_level=True,
    )

HEADERS = {"X-API-Key": API_SECRET_KEY} if API_SECRET_KEY else {}
TIMEOUT = 30  # seconds


# ── Helpers ───────────────────────────────────────────────────────────────────


def get(path: str) -> httpx.Response:
    with httpx.Client(timeout=TIMEOUT) as client:
        return client.get(f"{APP_URL}{path}", headers=HEADERS)


def post(path: str) -> httpx.Response:
    with httpx.Client(timeout=TIMEOUT) as client:
        return client.post(f"{APP_URL}{path}", headers=HEADERS)


# ── /health ───────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestHealthEndpoint:
    def test_returns_200(self) -> None:
        r = get("/health")
        assert r.status_code == 200, f"GET /health → {r.status_code}: {r.text}"

    def test_json_has_status_ok(self) -> None:
        r = get("/health")
        data = r.json()
        assert "status" in data, f"'status' key missing from /health response: {data}"
        assert data["status"] == "ok", f"Expected status='ok', got: {data['status']}"


# ── GET /rates/current ────────────────────────────────────────────────────────


@pytest.mark.integration
class TestRatesCurrentEndpoint:
    def test_returns_200(self) -> None:
        r = get("/rates/current")
        assert r.status_code == 200, f"GET /rates/current → {r.status_code}: {r.text}"

    def test_required_fields_present(self) -> None:
        data = get("/rates/current").json()
        required = ("ils_to_usdt", "usd_to_usdt", "euro_to_usdt", "fetched_at", "is_fresh")
        missing = [f for f in required if f not in data]
        assert not missing, f"Missing fields in /rates/current response: {missing}"

    def test_rate_values_are_positive(self) -> None:
        data = get("/rates/current").json()
        assert data["ils_to_usdt"] > 0, f"ils_to_usdt should be > 0, got {data['ils_to_usdt']}"
        assert data["usd_to_usdt"] > 0, f"usd_to_usdt should be > 0, got {data['usd_to_usdt']}"
        assert data["euro_to_usdt"] > 0, f"euro_to_usdt should be > 0, got {data['euro_to_usdt']}"

    def test_usd_rate_is_exactly_one(self) -> None:
        data = get("/rates/current").json()
        assert data["usd_to_usdt"] == 1.0, (
            f"USD/USDT peg should be 1.0, got {data['usd_to_usdt']}"
        )

    def test_fetched_at_is_nonempty(self) -> None:
        data = get("/rates/current").json()
        assert data["fetched_at"], "fetched_at should not be empty/null"

    def test_is_fresh_is_boolean(self) -> None:
        data = get("/rates/current").json()
        assert isinstance(data["is_fresh"], bool), (
            f"is_fresh should be a boolean, got {type(data['is_fresh'])}"
        )


# ── POST /rates/refresh ───────────────────────────────────────────────────────


@pytest.mark.integration
class TestRatesRefreshEndpoint:
    def test_returns_200(self) -> None:
        r = post("/rates/refresh")
        assert r.status_code == 200, f"POST /rates/refresh → {r.status_code}: {r.text}"

    def test_required_fields_present(self) -> None:
        data = post("/rates/refresh").json()
        required = (
            "ils_to_usdt",
            "usd_to_usdt",
            "euro_to_usdt",
            "fetched_at",
            "is_fresh",
            "refreshed",
        )
        missing = [f for f in required if f not in data]
        assert not missing, f"Missing fields in /rates/refresh response: {missing}"

    def test_refreshed_is_boolean(self) -> None:
        data = post("/rates/refresh").json()
        assert isinstance(data["refreshed"], bool), (
            f"'refreshed' should be a boolean, got {type(data['refreshed'])}"
        )

    def test_too_soon_returns_reason(self) -> None:
        """Two rapid calls: second should return refreshed=False with reason='too_soon'."""
        first = post("/rates/refresh").json()
        if first.get("refreshed") is True:
            second = post("/rates/refresh").json()
            assert second["refreshed"] is False, (
                "Second immediate refresh should be blocked"
            )
            assert second.get("reason") == "too_soon", (
                f"Expected reason='too_soon', got: {second.get('reason')}"
            )


# ── PostgreSQL rate_snapshots table ───────────────────────────────────────────

_DB_SKIP = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping DB persistence tests",
)


def _run(coro):  # type: ignore[return]
    """Run a coroutine in a fresh event loop (compatible with pytest-asyncio default mode)."""
    return asyncio.run(coro)


@pytest.mark.integration
class TestRateSnapshotsDB:
    """Verify that the rate_snapshots table exists and contains persisted data."""

    @_DB_SKIP
    def test_table_exists(self) -> None:
        """rate_snapshots table must be present in the public schema."""

        async def _check() -> bool:
            import asyncpg  # noqa: PLC0415

            conn = await asyncpg.connect(DATABASE_URL)
            try:
                row = await conn.fetchrow(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM information_schema.tables"
                    "  WHERE table_schema = 'public'"
                    "  AND table_name = 'rate_snapshots'"
                    ")"
                )
                return bool(row[0])
            finally:
                await conn.close()

        assert _run(_check()), "Table 'rate_snapshots' not found in the database"

    @_DB_SKIP
    def test_table_has_rows(self) -> None:
        """rate_snapshots must contain at least one persisted row."""

        async def _count() -> int:
            import asyncpg  # noqa: PLC0415

            conn = await asyncpg.connect(DATABASE_URL)
            try:
                row = await conn.fetchrow("SELECT COUNT(*) FROM rate_snapshots")
                return int(row[0])
            finally:
                await conn.close()

        count = _run(_count())
        assert count > 0, (
            f"rate_snapshots is empty — expected at least 1 row, found {count}"
        )

    @_DB_SKIP
    def test_latest_row_has_valid_rates(self) -> None:
        """Most recent snapshot row should have non-zero rate values and a timestamp."""

        async def _latest() -> dict:
            import asyncpg  # noqa: PLC0415

            conn = await asyncpg.connect(DATABASE_URL)
            try:
                # Discover columns dynamically to be resilient to naming variations
                cols = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema = 'public' AND table_name = 'rate_snapshots'"
                )
                col_names = [c["column_name"] for c in cols]

                row = await conn.fetchrow(
                    "SELECT * FROM rate_snapshots ORDER BY fetched_at DESC LIMIT 1"
                )
                return dict(zip(col_names, row)) if row else {}
            finally:
                await conn.close()

        row = _run(_latest())
        assert row, "No rows found in rate_snapshots"

        # Find rate columns (tolerates ils_to_usdt or ils_rate naming conventions)
        ils_col = next((k for k in row if "ils" in k.lower()), None)
        usd_col = next((k for k in row if "usd" in k.lower()), None)
        eur_col = next((k for k in row if "eur" in k.lower()), None)
        ts_col = next((k for k in row if "fetch" in k.lower() or "created" in k.lower()), None)

        assert ils_col, f"No ILS rate column found in rate_snapshots. Columns: {list(row)}"
        assert usd_col, f"No USD rate column found in rate_snapshots. Columns: {list(row)}"
        assert eur_col, f"No EUR rate column found in rate_snapshots. Columns: {list(row)}"
        assert ts_col, f"No timestamp column found in rate_snapshots. Columns: {list(row)}"

        assert float(row[ils_col]) > 0, f"{ils_col} should be > 0, got {row[ils_col]}"
        assert float(row[usd_col]) > 0, f"{usd_col} should be > 0, got {row[usd_col]}"
        assert float(row[eur_col]) > 0, f"{eur_col} should be > 0, got {row[eur_col]}"
        assert row[ts_col] is not None, f"{ts_col} should not be NULL"

    @_DB_SKIP
    def test_refresh_persists_new_snapshot(self) -> None:
        """
        Calling POST /rates/refresh (when not blocked by 60s guard) must insert
        a new row into rate_snapshots.
        """

        async def _count() -> int:
            import asyncpg  # noqa: PLC0415

            conn = await asyncpg.connect(DATABASE_URL)
            try:
                row = await conn.fetchrow("SELECT COUNT(*) FROM rate_snapshots")
                return int(row[0])
            finally:
                await conn.close()

        count_before = _run(_count())

        r = post("/rates/refresh")
        assert r.status_code == 200, f"POST /rates/refresh → {r.status_code}: {r.text}"
        data = r.json()

        if data.get("refreshed") is True:
            # Give the DB write a moment to commit
            time.sleep(1)
            count_after = _run(_count())
            assert count_after > count_before, (
                f"Refresh reported success but rate_snapshots row count did not increase "
                f"(before={count_before}, after={count_after})"
            )
        else:
            # Refresh was blocked by 60s guard — still a valid test pass
            pytest.skip(
                f"Refresh blocked (reason={data.get('reason')!r}) — "
                "re-run after 60 s to test snapshot insertion"
            )
