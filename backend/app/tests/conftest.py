"""Shared test fixtures.

Every test runs with `DEMO_MODE=true` and must not call an external API. See
`.kiro/steering/testing.md`.

Schema is created and dropped per test rather than truncated between tests. It costs
a few tens of milliseconds for a handful of tables and buys complete isolation, which
matters more here: the ownership tests in this feature are the ones that would be
worthless if state leaked between cases.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401  — registers every table on Base.metadata
from app.db import Base, dispose_engine, get_engine, get_session_factory
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


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A session for asserting directly against rows.

    Used sparingly. Most behaviour belongs at the HTTP seam, but a few invariants are
    about what is in the database rather than what the API returns — that bytes are
    stored in a column rather than a filesystem path, for instance, which an API
    round trip cannot distinguish while the development disk still exists.
    """
    async with get_session_factory()() as db_session:
        yield db_session


REAL_RESUME_ENV_VAR = "REACHLY_REAL_RESUME_PDF"


@pytest.fixture
def real_resume_pdf() -> bytes:
    """A genuine resume PDF from outside the repository, or skip.

    Tests using this validate extraction against real output — the kind of document a
    student actually uploads, produced by LaTeX or Word rather than by our own
    generator, which can only contain the mess we thought to put in it.

    The file is deliberately **not** in the repository. This repository is public, and a
    real resume carries a name, phone number and email address. Point the environment
    variable at a file anywhere outside the project:

        $env:REACHLY_REAL_RESUME_PDF = "C:\\path\\to\\resume.pdf"

    When it is unset these tests skip rather than fail, so a fresh clone and CI both
    pass. `pytest -rs` lists them as skipped with this reason, so a skip is never
    mistaken for a pass.
    """
    configured = os.environ.get(REAL_RESUME_ENV_VAR)
    if not configured:
        pytest.skip(f"{REAL_RESUME_ENV_VAR} is not set")
    path = Path(configured)
    if not path.is_file():
        pytest.skip(f"{REAL_RESUME_ENV_VAR} points at a missing file: {path}")
    return path.read_bytes()
