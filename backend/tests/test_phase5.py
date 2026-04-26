"""Phase 5 acceptance tests — local stdio MCP server.

Run with: pytest -m phase5
"""

import importlib.util
import os
import pytest

pytestmark = pytest.mark.phase5

MCP_SERVER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "mcp_server")


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    return mod, spec


@pytest.mark.phase5
def test_mcp_server_directory_exists():
    assert os.path.isdir(MCP_SERVER_DIR)


@pytest.mark.phase5
def test_mcp_server_has_required_files():
    required = ["server.py", "db.py", "pagination.py", "requirements.txt"]
    for f in required:
        assert os.path.isfile(os.path.join(MCP_SERVER_DIR, f)), f"Missing: {f}"


@pytest.mark.phase5
def test_mcp_tools_directory_has_all_modules():
    tools_dir = os.path.join(MCP_SERVER_DIR, "tools")
    required = [
        "users.py", "calculations.py", "saved_deals.py",
        "sessions.py", "activity.py", "experiments.py",
        "devices.py", "errors.py",
    ]
    for f in required:
        assert os.path.isfile(os.path.join(tools_dir, f)), f"Missing tool: {f}"


@pytest.mark.phase5
def test_pagination_clamp_limit():
    spec = importlib.util.spec_from_file_location(
        "pagination", os.path.join(MCP_SERVER_DIR, "pagination.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.clamp_limit(None) == mod.DEFAULT_LIMIT
    assert mod.clamp_limit(1000) == mod.MAX_LIMIT
    assert mod.clamp_limit(10) == 10


@pytest.mark.phase5
def test_pagination_build_next_cursor_empty():
    spec = importlib.util.spec_from_file_location(
        "pagination", os.path.join(MCP_SERVER_DIR, "pagination.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.build_next_cursor([]) is None


@pytest.mark.phase5
def test_pagination_build_next_cursor_returns_last_id():
    spec = importlib.util.spec_from_file_location(
        "pagination", os.path.join(MCP_SERVER_DIR, "pagination.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = [{"id": "aaa"}, {"id": "bbb"}, {"id": "ccc"}]
    assert mod.build_next_cursor(rows) == "ccc"


@pytest.mark.phase5
def test_server_defines_10_tools():
    """server.py must declare exactly 10 tools."""
    server_path = os.path.join(MCP_SERVER_DIR, "server.py")
    with open(server_path) as f:
        content = f.read()
    # Count Tool( occurrences
    assert content.count('Tool(') == 10


@pytest.mark.phase5
def test_server_tool_names_complete():
    server_path = os.path.join(MCP_SERVER_DIR, "server.py")
    with open(server_path) as f:
        content = f.read()
    expected_tools = [
        "list_users", "get_user_summary", "list_calculations",
        "get_calculation", "list_saved_deals", "get_session_journey",
        "daily_activity", "experiment_stats", "device_breakdown",
        "list_error_events",
    ]
    for tool in expected_tools:
        assert f'"{tool}"' in content, f"Tool {tool} not found in server.py"


@pytest.mark.phase5
def test_mcp_requirements_has_mcp_package():
    req_path = os.path.join(MCP_SERVER_DIR, "requirements.txt")
    with open(req_path) as f:
        content = f.read()
    assert "mcp" in content
    assert "asyncpg" in content
