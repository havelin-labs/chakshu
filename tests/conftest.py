"""Shared fixtures.

Tests run against a throwaway `<name>_test` database next to the one in
CHAKSHU_DATABASE_URL. It's dropped and recreated once per test session and
migrated with the real Alembic migrations, so tests also prove the migrations work.
"""

import asyncio
import os
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

os.environ.setdefault("CHAKSHU_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters")


def _test_database_url() -> str:
    from chakshu.core.config import Settings

    url = make_url(Settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


async def _recreate_database(url: str) -> None:
    target = make_url(url)
    admin = create_async_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    await admin.dispose()


def _reset_caches() -> None:
    from chakshu.core.config import get_settings
    from chakshu.db.session import get_engine, get_sessionmaker

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def database() -> str:
    url = _test_database_url()
    asyncio.run(_recreate_database(url))
    os.environ["CHAKSHU_DATABASE_URL"] = url
    _reset_caches()

    from chakshu.cli import main

    main(["migrate"])
    return url


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client that calls the app in-process, on the test event loop."""
    from chakshu.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """A session on the test database. Tables are emptied after each test."""
    from chakshu.db.base import Base
    from chakshu.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        yield session
        await session.rollback()
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        await session.execute(text(f"TRUNCATE {tables} CASCADE"))
        await session.commit()
