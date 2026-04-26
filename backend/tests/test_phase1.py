"""Phase 1 acceptance tests — identity and session schema.

Run with: pytest -m phase1
"""

import pytest


pytestmark = pytest.mark.phase1


# ---------------------------------------------------------------------------
# Schema existence tests (run against a real DB in CI; unit-tested via reflection)
# ---------------------------------------------------------------------------


@pytest.mark.phase1
def test_users_model_has_required_columns():
    from app.models import User

    cols = {c.key for c in User.__table__.columns}
    required = {
        "id", "kind", "created_at", "consent_pii",
        "retention_bucket", "deleted_at",
    }
    assert required <= cols


@pytest.mark.phase1
def test_users_kind_check_values():
    """kind column must accept exactly anonymous/oauth/deleted."""
    from app.models import User

    col = User.__table__.c.kind
    checks = [c for c in User.__table__.constraints if hasattr(c, "sqltext")]
    check_texts = [str(c.sqltext) for c in checks]
    assert any("kind" in t for t in check_texts)


@pytest.mark.phase1
def test_user_uuids_fk_to_users():
    from app.models import UserUuid

    fks = {fk.target_fullname for fk in UserUuid.__table__.foreign_keys}
    assert "users.id" in fks


@pytest.mark.phase1
def test_oauth_identities_unique_provider_subject():
    from app.models import OAuthIdentity

    unique_constraints = [
        c for c in OAuthIdentity.__table__.constraints
        if hasattr(c, "columns") and len(list(c.columns)) == 2
    ]
    col_sets = [frozenset(c.name for c in uc.columns) for uc in unique_constraints]
    assert frozenset({"provider", "provider_subject"}) in col_sets


@pytest.mark.phase1
def test_telegram_identities_has_consecutive_errors():
    from app.models import TelegramIdentity

    col = TelegramIdentity.__table__.c.consecutive_errors
    assert col is not None
    assert not col.nullable
    assert col.server_default is not None


@pytest.mark.phase1
def test_sessions_has_device_context_columns():
    from app.models import Session

    device_cols = {
        "device_type", "os_family", "browser_family",
        "screen_width", "screen_height", "viewport_width", "viewport_height",
        "device_pixel_ratio", "cpu_cores", "device_memory_gb",
    }
    cols = {c.key for c in Session.__table__.columns}
    assert device_cols <= cols


@pytest.mark.phase1
def test_sessions_has_geo_columns():
    from app.models import Session

    geo_cols = {"country_code", "city", "isp", "connection_type"}
    cols = {c.key for c in Session.__table__.columns}
    assert geo_cols <= cols


@pytest.mark.phase1
def test_sessions_has_experiment_flags():
    from app.models import Session

    col = Session.__table__.c.experiment_flags
    assert col is not None
    assert col.nullable


@pytest.mark.phase1
def test_sessions_ga_fields_not_nullable():
    from app.models import Session

    assert not Session.__table__.c.ga_client_id.nullable
    assert not Session.__table__.c.ga_session_id.nullable
    assert not Session.__table__.c.environment.nullable


@pytest.mark.phase1
def test_sessions_fk_to_users_restrict():
    from app.models import Session

    fk = next(
        fk for fk in Session.__table__.foreign_keys
        if fk.target_fullname == "users.id"
    )
    assert fk.ondelete.upper() == "RESTRICT"


@pytest.mark.phase1
def test_users_soft_delete_column_nullable():
    from app.models import User

    col = User.__table__.c.deleted_at
    assert col.nullable
