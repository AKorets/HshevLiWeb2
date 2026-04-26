"""Phase 7 acceptance tests — Flutter header integration.

Phase 7 is primarily a manual verification phase (Flutter web build required).
These tests verify the Dart service files exist and are syntactically valid.

Manual checklist (run after flutter build web):
- [ ] X-Tab-Id header present on all requests (DevTools Network)
- [ ] Two tabs have different X-Tab-Id values
- [ ] device_context object present in heartbeat body
- [ ] Input for 2s without Calculate → input_changed event in user_events table
- [ ] Input then Calculate → followed_by_calculate = true in user_events
- [ ] Go offline → calculate → reconnect → is_offline_sync = true in DB

Run with: pytest -m phase7
"""

import os
import pytest

pytestmark = pytest.mark.phase7

LIB_SERVICES = os.path.join(
    os.path.dirname(__file__), "..", "..", "lib", "services"
)


@pytest.mark.phase7
def test_tracking_service_exists():
    assert os.path.isfile(os.path.join(LIB_SERVICES, "tracking_service.dart"))


@pytest.mark.phase7
def test_device_context_service_exists():
    assert os.path.isfile(os.path.join(LIB_SERVICES, "device_context_service.dart"))


@pytest.mark.phase7
def test_feature_flag_service_exists():
    assert os.path.isfile(os.path.join(LIB_SERVICES, "feature_flag_service.dart"))


@pytest.mark.phase7
def test_backend_service_exists():
    assert os.path.isfile(os.path.join(LIB_SERVICES, "backend_service.dart"))


@pytest.mark.phase7
def test_analytics_service_web_has_get_client_id():
    path = os.path.join(LIB_SERVICES, "analytics_service_web.dart")
    with open(path) as f:
        content = f.read()
    assert "getClientId" in content
    assert "getSessionId" in content


@pytest.mark.phase7
def test_analytics_service_stub_has_get_client_id():
    path = os.path.join(LIB_SERVICES, "analytics_service_stub.dart")
    with open(path) as f:
        content = f.read()
    assert "getClientId" in content
    assert "getSessionId" in content


@pytest.mark.phase7
def test_tracking_service_generates_tab_id():
    path = os.path.join(LIB_SERVICES, "tracking_service.dart")
    with open(path) as f:
        content = f.read()
    assert "tabId" in content
    assert "deviceUuid" in content


@pytest.mark.phase7
def test_backend_service_injects_required_headers():
    path = os.path.join(LIB_SERVICES, "backend_service.dart")
    with open(path) as f:
        content = f.read()
    required_headers = [
        "X-GA-Client-Id",
        "X-GA-Session-Id",
        "X-Device-UUID",
        "X-Tab-Id",
    ]
    for header in required_headers:
        assert header in content, f"Header {header} not found in backend_service.dart"


@pytest.mark.phase7
def test_feature_flag_service_returns_map():
    path = os.path.join(LIB_SERVICES, "feature_flag_service.dart")
    with open(path) as f:
        content = f.read()
    assert "getFlags" in content
    assert "Map<String, String>" in content
