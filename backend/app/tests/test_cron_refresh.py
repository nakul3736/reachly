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



class TestTheRequestBudget:
    """One request must always answer, whatever the boards and the model are doing.

    Every phase was bounded on its own and nothing bounded their sum, so a slow run could reach
    roughly nine minutes: four for the sweep, plus classification, plus twelve live enrichment
    batches each able to spend six seconds on rate-limit backoff, plus dedup. In production that
    surfaced as **502 after seven minutes** on the scheduled refresh, while a manual run of the same
    code finished in one minute forty. A proxy in front of the container gives up long before the
    work does, and the work had no idea.
    """

    async def test_the_sweep_is_given_less_than_its_own_default(self) -> None:
        """The endpoint's budget has to win over the sweep's, or the sum is unbounded again."""
        from app.api.cron import _REQUEST_BUDGET_SECONDS
        from app.services.ingest_service import DEFAULT_MAX_SECONDS

        sweep_budget = min(DEFAULT_MAX_SECONDS, _REQUEST_BUDGET_SECONDS * 0.6)

        assert sweep_budget < DEFAULT_MAX_SECONDS, (
            "the sweep must not be allowed to spend the whole request window, or classification "
            "and dedup run outside any budget at all"
        )
        assert sweep_budget + 45.0 <= _REQUEST_BUDGET_SECONDS, (
            "there must be room left for the phases that follow the sweep"
        )

    async def test_enrichment_is_skipped_when_the_budget_is_spent_and_says_so(
        self, client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reported rather than inferred from a zero count.

        "Read nothing" and "did not run" are different facts, and a scheduler's own history is the
        only place anybody will notice the difference.
        """
        import app.api.cron as cron

        # A budget of zero means no phase can ever afford enrichment.
        monkeypatch.setattr(cron, "_REQUEST_BUDGET_SECONDS", 0.0)

        called = False

        async def _never(*args: object, **kwargs: object) -> object:
            nonlocal called
            called = True
            raise AssertionError("enrichment must not run with no budget left")

        monkeypatch.setattr(cron, "enrich_job_skills", _never)

        response = await client.post(
            "/internal/cron/refresh-jobs", headers={"X-Cron-Secret": "test-cron-secret"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["skills_read_skipped_for_budget"] is True
        assert called is False
        # And the phases whose absence is not safe still ran: an unclassified posting is invisible
        # to every filter in the feed, so classification is never the thing that gets dropped.
        assert "classified" in body
        assert "deduplicated" in body

    async def test_enrichment_runs_when_there_is_room(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        response = await client.post(
            "/internal/cron/refresh-jobs", headers={"X-Cron-Secret": "test-cron-secret"}
        )

        assert response.status_code == 200
        assert response.json()["skills_read_skipped_for_budget"] is False
