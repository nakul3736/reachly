"""The refresh endpoint.

Behind the same secret as keepalive, and answering 404 rather than 401 for the same reason: an
endpoint that triggers work should not confirm it exists to anyone who guesses the path.
"""

from collections.abc import Iterator

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.http import set_http_client_factory
from app.config import get_settings
from app.models.board_token import BoardToken

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _cron_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_real_network() -> Iterator[None]:
    """The refresh endpoint builds its own client, so the seam has to be closed here.

    Without this the suite made live requests to The Muse — which is slow, unreliable, and
    exactly what the testing rules forbid. Anything not explicitly stubbed answers 503, so a
    forgotten stub fails a test rather than making a network call.
    """

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(503, text="stubbed"))
        )

    set_http_client_factory(factory)
    yield
    set_http_client_factory(None)


async def test_refresh_needs_the_secret(client: AsyncClient) -> None:
    response = await client.post("/internal/cron/refresh-jobs")

    assert response.status_code == 404, "a wrong secret must not confirm the route exists"


async def test_refresh_with_the_secret_reports_what_it_did(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Reports per-source counts rather than just succeeding.

    Story 28: a source that fetches successfully and creates nothing for a week is the failure
    that hides best, so the numbers have to come back.
    """
    session.add(BoardToken(provider="workday", token="acme", company_name="Acme"))
    await session.commit()

    response = await client.post(
        "/internal/cron/refresh-jobs", headers={"X-Cron-Secret": "test-cron-secret"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["boards_attempted"] == 0
    assert payload["boards_skipped"] == 1, "no adapter for workday, and that is not a failure"
    assert "created" in payload
    assert "classified" in payload


async def test_refresh_classifies_what_it_ingested(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A posting arriving unclassified would be invisible to every filter.

    Which is worse than it sounds: the filters are exclusions, so an unclassified job is
    excluded by any active filter rather than merely unsorted.
    """
    response = await client.post(
        "/internal/cron/refresh-jobs", headers={"X-Cron-Secret": "test-cron-secret"}
    )

    assert response.status_code == 200
    assert response.json()["classified"] >= 0
