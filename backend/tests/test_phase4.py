"""Phase 4 acceptance tests — MCP read layer (DB-side).

Run with: pytest -m phase4
"""

import importlib.util
import os
import pytest

pytestmark = pytest.mark.phase4

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
MCP_QUERIES_DIR = os.path.join(SCRIPTS_DIR, "mcp_queries")


@pytest.mark.phase4
def test_all_mcp_sql_files_exist():
    expected = [
        "list_users.sql",
        "get_user_summary.sql",
        "list_calculations.sql",
        "get_calculation.sql",
        "list_saved_deals.sql",
        "get_session_journey.sql",
        "daily_activity.sql",
        "experiment_stats.sql",
        "device_breakdown.sql",
        "list_error_events.sql",
    ]
    for filename in expected:
        path = os.path.join(MCP_QUERIES_DIR, filename)
        assert os.path.isfile(path), f"Missing SQL file: {filename}"


@pytest.mark.phase4
def test_refresh_script_importable():
    path = os.path.join(SCRIPTS_DIR, "refresh_mcp_views.py")
    spec = importlib.util.spec_from_file_location("refresh_mcp_views", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "refresh_views")
    assert hasattr(mod, "MATERIALIZED_VIEWS")


@pytest.mark.phase4
def test_refresh_script_includes_all_mat_views():
    path = os.path.join(SCRIPTS_DIR, "refresh_mcp_views.py")
    spec = importlib.util.spec_from_file_location("refresh_mcp_views", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    expected = {
        "mcp_readonly.vw_user_summary",
        "mcp_readonly.vw_daily_activity",
        "mcp_readonly.vw_device_breakdown",
    }
    assert expected <= set(mod.MATERIALIZED_VIEWS)


@pytest.mark.phase4
def test_verify_script_importable():
    path = os.path.join(SCRIPTS_DIR, "verify_mcp_schema.py")
    spec = importlib.util.spec_from_file_location("verify_mcp_schema", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "verify")
    assert hasattr(mod, "EXPECTED_VIEWS")


@pytest.mark.phase4
def test_verify_script_expected_views_complete():
    path = os.path.join(SCRIPTS_DIR, "verify_mcp_schema.py")
    spec = importlib.util.spec_from_file_location("verify_mcp_schema", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    required = {
        "vw_users", "vw_sessions", "vw_calculations", "vw_saved_deals",
        "vw_session_journey", "vw_error_events", "vw_experiment_stats",
        "vw_user_summary", "vw_daily_activity", "vw_device_breakdown",
    }
    assert required <= set(mod.EXPECTED_VIEWS)


@pytest.mark.phase4
def test_mcp_sql_files_have_parameter_comments():
    """Each SQL file must start with a -- MCP tool: comment."""
    for filename in os.listdir(MCP_QUERIES_DIR):
        if not filename.endswith(".sql"):
            continue
        path = os.path.join(MCP_QUERIES_DIR, filename)
        with open(path) as f:
            first_line = f.readline()
        assert first_line.startswith("-- MCP tool:"), (
            f"{filename} must start with '-- MCP tool:' comment"
        )


@pytest.mark.phase4
def test_mcp_readonly_migration_exists():
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "alembic", "versions"
    )
    files = os.listdir(migrations_dir)
    assert any("0005" in f for f in files), "Migration 0005_mcp_readonly.py not found"
