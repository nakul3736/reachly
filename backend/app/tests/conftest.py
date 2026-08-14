"""Shared test fixtures.

Every test runs with `DEMO_MODE=true` and must not call an external API. See
`.kiro/steering/testing.md`.
"""

from collections.abc import AsyncIterator

import pytest

from app.db import dispose_engine


@pytest.fixture(autouse=True)
async def _fresh_engine_per_test() -> AsyncIterator[None]:
    """Give each test its own engine.

    pytest-asyncio runs each test on a new event loop, and an asyncpg connection
    cannot outlive the loop it was opened on. Disposing afterwards means the next
    test builds a fresh pool on its own loop instead of inheriting a dead one.
    """
    yield
    await dispose_engine()
