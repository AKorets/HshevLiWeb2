"""Phase 10 acceptance tests — retention, purge, and partition management.

Run with: pytest -m phase10
"""

import importlib.util
import os
import pytest

pytestmark = pytest.mark.phase10

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")


def _load(name: str):
    path = os.path.join(SCRIPTS_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.phase10
def test_purge_script_importable():
    mod = _load("purge_old_data")
    assert hasattr(mod, "purge")
    assert hasattr(mod, "RETENTION_INTERVALS")


@pytest.mark.phase10
def test_purge_script_retention_intervals():
    mod = _load("purge_old_data")
    assert "standard" in mod.RETENTION_INTERVALS
    assert "minimal" in mod.RETENTION_INTERVALS
    assert "25" in mod.RETENTION_INTERVALS["standard"]
    assert "90" in mod.RETENTION_INTERVALS["minimal"]


@pytest.mark.phase10
def test_purge_script_covers_all_tables():
    mod = _load("purge_old_data")
    tables = {t[0] for t in mod.PURGE_TARGETS}
    assert {"calculations", "user_events", "saved_deals", "sessions"} <= tables


@pytest.mark.phase10
def test_anonymize_script_importable():
    mod = _load("anonymize_deleted_users")
    assert hasattr(mod, "anonymize")


@pytest.mark.phase10
def test_anonymize_script_clears_pii_columns():
    path = os.path.join(SCRIPTS_DIR, "anonymize_deleted_users.py")
    with open(path) as f:
        content = f.read()
    pii_cols = ["user_agent", "ip_hash", "country_code", "city", "isp", "locale"]
    for col in pii_cols:
        assert col in content, f"PII column {col} not cleared in anonymize script"


@pytest.mark.phase10
def test_create_partitions_script_importable():
    mod = _load("create_partitions")
    assert hasattr(mod, "create_partitions")
    assert hasattr(mod, "PARTITIONED_TABLES")


@pytest.mark.phase10
def test_create_partitions_covers_calculations_and_events():
    mod = _load("create_partitions")
    assert "calculations" in mod.PARTITIONED_TABLES
    assert "user_events" in mod.PARTITIONED_TABLES


@pytest.mark.phase10
def test_refresh_mcp_views_covers_all_mat_views():
    mod = _load("refresh_mcp_views")
    assert len(mod.MATERIALIZED_VIEWS) >= 3
