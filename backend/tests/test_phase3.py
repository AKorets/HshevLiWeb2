"""Phase 3 acceptance tests — saved_deals, telegram_deal_sends, user_events.

Run with: pytest -m phase3
"""

import pytest

pytestmark = pytest.mark.phase3


@pytest.mark.phase3
def test_saved_deals_fk_to_calculations():
    from app.models import SavedDeal

    fks = {fk.target_fullname for fk in SavedDeal.__table__.foreign_keys}
    assert "calculations.id" in fks


@pytest.mark.phase3
def test_saved_deals_has_headline_fields():
    from app.models import SavedDeal

    headline_cols = {
        "headline_sell_currency",
        "headline_buy_currency",
        "headline_sell_amount",
        "headline_receive_amount",
    }
    cols = {c.key for c in SavedDeal.__table__.columns}
    assert headline_cols <= cols


@pytest.mark.phase3
def test_telegram_deal_sends_status_column():
    from app.models import TelegramDealSend

    col = TelegramDealSend.__table__.c.status
    assert not col.nullable


@pytest.mark.phase3
def test_telegram_deal_sends_cascade_from_saved_deal():
    from app.models import TelegramDealSend

    fk = next(
        fk for fk in TelegramDealSend.__table__.foreign_keys
        if fk.target_fullname == "saved_deals.id"
    )
    assert fk.ondelete.upper() == "CASCADE"


@pytest.mark.phase3
def test_user_events_has_tab_id():
    from app.models import UserEvent

    col = UserEvent.__table__.c.tab_id
    assert col is not None
    assert col.nullable


@pytest.mark.phase3
def test_user_events_event_params_jsonb():
    from app.models import UserEvent
    from sqlalchemy.dialects.postgresql import JSONB

    col = UserEvent.__table__.c.event_params
    assert isinstance(col.type, JSONB)


@pytest.mark.phase3
def test_user_events_not_nullable_fields():
    from app.models import UserEvent

    for col_name in ("event_name", "occurred_at"):
        col = UserEvent.__table__.c[col_name]
        assert not col.nullable, f"{col_name} should not be nullable"


@pytest.mark.phase3
def test_saved_deals_note_nullable():
    from app.models import SavedDeal

    assert SavedDeal.__table__.c.note.nullable


@pytest.mark.phase3
def test_telegram_deal_sends_no_pii_in_delivery():
    """Delivery target is telegram_chat_id (bigint), not telegram_username (text)."""
    from app.models import TelegramDealSend

    chat_id_col = TelegramDealSend.__table__.c.telegram_chat_id
    username_col = TelegramDealSend.__table__.c.telegram_username

    assert not chat_id_col.nullable
    assert username_col.nullable
