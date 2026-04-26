"""Phase 8 acceptance tests — OAuth identity & user_merges.

Run with: pytest -m phase8
"""

import pytest

pytestmark = pytest.mark.phase8


@pytest.mark.phase8
def test_user_merge_model_exists():
    from app.models import UserMerge

    cols = {c.key for c in UserMerge.__table__.columns}
    assert {"id", "from_user_id", "to_user_id", "merge_reason", "merged_at"} <= cols


@pytest.mark.phase8
def test_user_merge_to_user_id_fk():
    from app.models import UserMerge

    fks = {fk.target_fullname for fk in UserMerge.__table__.foreign_keys}
    assert "users.id" in fks


@pytest.mark.phase8
def test_user_merge_from_user_id_no_fk():
    """from_user_id is intentionally NOT FK'd — the anon user may be soft-deleted."""
    from app.models import UserMerge

    fk_targets = {fk.target_fullname for fk in UserMerge.__table__.foreign_keys}
    # Only to_user_id should be FK'd to users.id
    assert len([f for f in fk_targets if "users" in f]) == 1


@pytest.mark.phase8
def test_auth_router_registered():
    from app.main import app

    routes = [r.path for r in app.routes]
    assert "/auth/link-identity" in routes


@pytest.mark.phase8
def test_link_identity_request_schema():
    from app.routers.auth import LinkIdentityRequest

    fields = set(LinkIdentityRequest.model_fields.keys())
    assert {"provider", "provider_subject", "device_uuid"} <= fields
    assert "email" in fields  # optional


@pytest.mark.phase8
def test_migration_0006_exists():
    import os
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "alembic", "versions"
    )
    files = os.listdir(migrations_dir)
    assert any("0006" in f for f in files)


@pytest.mark.phase8
def test_oauth_identity_email_nullable():
    from app.models import OAuthIdentity

    assert OAuthIdentity.__table__.c.email.nullable
