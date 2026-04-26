"""Phase 6 acceptance tests — backend ingest endpoints.

Run with: pytest -m phase6
"""

import pytest
from unittest.mock import patch

pytestmark = pytest.mark.phase6


@pytest.mark.phase6
def test_ip_hash_returns_32_bytes():
    import os
    with patch.dict(os.environ, {"GA_IP_HASH_SALT": "test-salt"}):
        from app.services.ip_hash import hash_ip
        result = hash_ip("1.2.3.4")
        assert isinstance(result, bytes)
        assert len(result) == 32


@pytest.mark.phase6
def test_ip_hash_same_ip_same_salt_deterministic():
    import os
    with patch.dict(os.environ, {"GA_IP_HASH_SALT": "test-salt"}):
        from app.services import ip_hash as ih_module
        ih_module._salt = None  # reset cache
        from app.services.ip_hash import hash_ip
        assert hash_ip("192.168.1.1") == hash_ip("192.168.1.1")


@pytest.mark.phase6
def test_ip_hash_different_ips_different_hashes():
    import os
    with patch.dict(os.environ, {"GA_IP_HASH_SALT": "test-salt"}):
        from app.services import ip_hash as ih_module
        ih_module._salt = None
        from app.services.ip_hash import hash_ip
        assert hash_ip("1.2.3.4") != hash_ip("5.6.7.8")


@pytest.mark.phase6
def test_device_context_clamps_screen_dimensions():
    from app.services.device_context import DeviceContext

    dc = DeviceContext(screen_width=99999, screen_height=-10)
    assert dc.screen_width == 32767
    assert dc.screen_height == 0


@pytest.mark.phase6
def test_device_context_accepts_valid_types():
    from app.services.device_context import DeviceContext

    dc = DeviceContext(device_type="mobile", connection_type="wifi")
    assert dc.device_type == "mobile"
    assert dc.connection_type == "wifi"


@pytest.mark.phase6
def test_geo_lookup_returns_geo_result_when_no_db():
    from app.services.geo_lookup import lookup, GeoResult

    result = lookup("1.2.3.4")
    assert isinstance(result, GeoResult)
    # Without GEOIP_DB_PATH set, all fields are None
    assert result.country_code is None


@pytest.mark.phase6
def test_sessions_router_is_registered():
    from app.main import app

    routes = [r.path for r in app.routes]
    assert "/sessions/heartbeat" in routes


@pytest.mark.phase6
def test_calculations_router_is_registered():
    from app.main import app

    routes = [r.path for r in app.routes]
    assert "/calculations" in routes


@pytest.mark.phase6
def test_saved_deals_router_is_registered():
    from app.main import app

    routes = [r.path for r in app.routes]
    assert "/saved-deals" in routes


@pytest.mark.phase6
def test_events_router_is_registered():
    from app.main import app

    routes = [r.path for r in app.routes]
    assert "/events" in routes


@pytest.mark.phase6
def test_calculation_in_schema_has_idempotency_field():
    from app.routers.calculations import CalculationIn

    fields = set(CalculationIn.model_fields.keys())
    assert "client_request_id" in fields
    assert "client_calculated_at" in fields
    assert "tab_id" in fields


@pytest.mark.phase6
def test_event_in_requires_event_name():
    from app.routers.events import EventIn

    fields = EventIn.model_fields
    assert "event_name" in fields
    assert fields["event_name"].is_required()
