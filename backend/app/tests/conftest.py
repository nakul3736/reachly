"""Shared test fixtures.

Every test runs with `DEMO_MODE=true` and must not call an external API. See
`.kiro/steering/testing.md`.

Schema is created and dropped per test rather than truncated between tests. It costs
a few tens of milliseconds for a handful of tables and buys complete isolation, which
matters more here: the ownership tests in this feature are the ones that would be
worthless if state leaked between cases.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

import app.models  # noqa: F401  — registers every table on Base.metadata
from app.db import Base, dispose_engine, get_engine
from app.main import app as fastapi_app


@pytest.fixture(autouse=True)
async def _schema() -> AsyncIterator[None]:
    """A fresh schema per test, on the test's own event loop.

    Creating tables directly rather than running migrations keeps tests fast. The
    migrations are exercised separately — see the round trip in ticket 01.
    """
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        # pytest-asyncio gives each test a new event loop, and an asyncpg
        # connection cannot outlive the loop it was opened on.
        await dispose_engine()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
