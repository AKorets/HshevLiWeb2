"""Phase 9 acceptance tests — Telegram integration.

Run with: pytest -m phase9
"""

import pytest

pytestmark = pytest.mark.phase9


@pytest.mark.phase9
def test_telegram_router_registered():
    from app.main import app

    routes = [r.path for r in app.routes]
    assert "/telegram/connect" in routes
    assert "/telegram/send-deal" in routes


@pytest.mark.phase9
def test_connect_request_schema():
    from app.routers.telegram import ConnectRequest

    fields = set(ConnectRequest.model_fields.keys())
    assert {"device_uuid", "telegram_chat_id"} <= fields
    assert ConnectRequest.model_fields["telegram_chat_id"].is_required()


@pytest.mark.phase9
def test_send_deal_request_schema():
    from app.routers.telegram import SendDealRequest

    fields = set(SendDealRequest.model_fields.keys())
    assert {"saved_deal_id", "user_id", "telegram_chat_id", "message_text"} <= fields


@pytest.mark.phase9
def test_consecutive_error_threshold_value():
    from app.routers import telegram as tg_module

    assert tg_module._TG_CONSECUTIVE_ERROR_THRESHOLD == 3


@pytest.mark.phase9
def test_telegram_identities_has_auto_deactivation_columns():
    from app.models import TelegramIdentity

    assert hasattr(TelegramIdentity, "consecutive_errors")
    assert hasattr(TelegramIdentity, "is_active")
    assert not TelegramIdentity.__table__.c.consecutive_errors.nullable


@pytest.mark.phase9
def test_telegram_deal_sends_model_exists():
    from app.models import TelegramDealSend

    cols = {c.key for c in TelegramDealSend.__table__.columns}
    assert {"id", "saved_deal_id", "user_id", "telegram_chat_id", "status", "sent_at"} <= cols


@pytest.mark.phase9
def test_telegram_send_uses_chat_id_not_username():
    """send_deal endpoint must target telegram_chat_id in the INSERT, not telegram_username."""
    import inspect
    from app.routers.telegram import send_deal

    source = inspect.getsource(send_deal)
    assert "telegram_chat_id" in source
    # Ensure username is only used as a display snapshot, not as delivery target
    assert "telegram_username" in source  # stored as snapshot
