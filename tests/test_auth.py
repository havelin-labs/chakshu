import uuid

from chakshu.core.config import get_settings
from chakshu.db.models import Installation
from chakshu.services import users


async def test_personal_account_owner_is_admin(db):
    db.add(
        Installation(
            id=uuid.uuid4(), github_id=1, account_github_id=10, account_login="Alice", account_type="User"
        )
    )
    await db.commit()

    assert await users.access(db, creds=None, login="alice") == (True, True)
    assert await users.access(db, creds=None, login="mallory") == (False, False)


async def test_configured_admins_are_always_admins(db, monkeypatch):
    monkeypatch.setenv("CHAKSHU_ADMINS", "Ops-Lead, other")
    get_settings.cache_clear()
    try:
        assert await users.access(db, creds=None, login="ops-lead") == (True, True)
    finally:
        get_settings.cache_clear()


async def test_session_has_no_user_until_sign_in(client):
    session = (await client.get("/api/session")).json()
    assert session["user"] is None


async def test_logout_requires_csrf(client):
    assert (await client.post("/api/auth/logout")).status_code == 403
    token = (await client.get("/api/session")).json()["csrf_token"]
    assert (await client.post("/api/auth/logout", headers={"X-CSRF-Token": token})).status_code == 200
