from sqlalchemy import select

from chakshu.db.models import Setting
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key


async def test_defaults_apply_when_unset(db):
    assert await store.get(db, Key.DEFAULT_MODEL) == "sonnet"
    assert await store.get(db, Key.ANTHROPIC_API_KEY) is None


async def test_secrets_are_encrypted_at_rest(db):
    await store.put(db, Key.ANTHROPIC_API_KEY, "sk-ant-secret")
    await db.commit()

    row = (await db.scalars(select(Setting).where(Setting.key == Key.ANTHROPIC_API_KEY.value))).one()
    assert row.is_secret
    assert "sk-ant-secret" not in row.value
    assert await store.get(db, Key.ANTHROPIC_API_KEY) == "sk-ant-secret"


async def test_put_overwrites(db):
    await store.put(db, Key.DEFAULT_MODEL, "opus")
    await store.put(db, Key.DEFAULT_MODEL, "haiku")
    await db.commit()
    assert await store.get(db, Key.DEFAULT_MODEL) == "haiku"


async def test_get_many_mixes_stored_and_defaults(db):
    await store.put_many(db, {Key.APP_SLUG: "chakshu-acme"})
    await db.commit()

    values = await store.get_many(db, Key.APP_SLUG, Key.REVIEWERS_REPO, Key.APP_ID)
    assert values == {Key.APP_SLUG: "chakshu-acme", Key.REVIEWERS_REPO: "chakshu-reviewers", Key.APP_ID: None}
