"""Phase 11 acceptance tests — session quality, stitching, advanced signals.

Run with: pytest -m phase11
"""

import pytest

pytestmark = pytest.mark.phase11


@pytest.mark.phase11
def test_session_stitcher_importable():
    from app.services.session_stitcher import (
        find_stitchable_session,
        stitch_session,
        _STITCH_WINDOW_MINUTES,
    )
    assert _STITCH_WINDOW_MINUTES == 30


@pytest.mark.phase11
def test_heartbeat_request_has_quality_fields():
    from app.routers.sessions import HeartbeatRequest

    fields = set(HeartbeatRequest.model_fields.keys())
    assert "scroll_depth_percent" in fields
    assert "time_to_first_action_ms" in fields
    assert "hesitation_before_calc_ms" in fields


@pytest.mark.phase11
def test_heartbeat_quality_fields_optional():
    from app.routers.sessions import HeartbeatRequest

    for field in ("scroll_depth_percent", "time_to_first_action_ms", "hesitation_before_calc_ms"):
        assert not HeartbeatRequest.model_fields[field].is_required(), (
            f"{field} should be optional"
        )


@pytest.mark.phase11
def test_migration_0007_exists():
    import os
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "alembic", "versions"
    )
    files = os.listdir(migrations_dir)
    assert any("0007" in f for f in files)


@pytest.mark.phase11
def test_migration_0007_adds_quality_columns():
    import os
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "alembic", "versions"
    )
    migration_file = next(f for f in os.listdir(migrations_dir) if "0007" in f)
    path = os.path.join(migrations_dir, migration_file)
    with open(path) as f:
        content = f.read()
    for col in ("scroll_depth_percent", "time_to_first_action_ms", "hesitation_before_calc_ms", "device_fingerprint_hash"):
        assert col in content, f"{col} not in migration 0007"


@pytest.mark.phase11
def test_heartbeat_response_includes_stitched_flag():
    """The heartbeat endpoint response must include a 'stitched' boolean."""
    import inspect
    from app.routers.sessions import heartbeat

    source = inspect.getsource(heartbeat)
    assert '"stitched"' in source or "'stitched'" in source


@pytest.mark.phase11
def test_stitch_window_is_30_minutes():
    from app.services.session_stitcher import _STITCH_WINDOW_MINUTES

    assert _STITCH_WINDOW_MINUTES == 30


@pytest.mark.phase11
def test_scroll_depth_uses_greatest():
    """heartbeat must use GREATEST to never decrease scroll_depth_percent."""
    import inspect
    from app.routers.sessions import heartbeat

    source = inspect.getsource(heartbeat)
    assert "GREATEST" in source
