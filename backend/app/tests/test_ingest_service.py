"""Ingesting a board into the index, through the transport seam.

The seam is the HTTP transport, not a `JobSource` protocol. Substituting here means the
adapter's normalisation, the status handling and the JSON decoding all run for real, and only
the socket is faked. A protocol with a fixture implementation would have replaced exactly the
code most likely to be wrong — the mistake ticket 06 made with `FixtureResumeParser`, where
demo mode ended up exercising a different program from production.
"""

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board_token import BoardToken
from app.models.job import Job
from app.services.ingest_service import ingest_board, refresh_all_boards
from app.tests.fixtures.job_payloads import GREENHOUSE_BOARD

pytestmark = pytest.mark.anyio


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=GREENHOUSE_BOARD)


async def _board(session: AsyncSession) -> BoardToken:
    board = BoardToken(provider="greenhouse", token="figma", company_name="Figma")
    session.add(board)
    await session.commit()
    return board


async def _count(session: AsyncSession) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(Job))).scalar_one()
    )


async def test_a_successful_fetch_puts_jobs_in_the_index(session: AsyncSession) -> None:
    board = await _board(session)

    async with _client(_ok) as client:
        result = await ingest_board(session, board, client=client)

    assert result.created == len(GREENHOUSE_BOARD["jobs"])
    assert await _count(session) == len(GREENHOUSE_BOARD["jobs"])


async def test_ingesting_the_same_payload_twice_creates_no_duplicates(
    session: AsyncSession,
) -> None:
    """Story 26 — a refresh re-run after a crash must not double the index."""
    board = await _board(session)

    async with _client(_ok) as client:
        first = await ingest_board(session, board, client=client)
        second = await ingest_board(session, board, client=client)

    assert first.created == len(GREENHOUSE_BOARD["jobs"])
    assert second.created == 0
    assert second.updated == len(GREENHOUSE_BOARD["jobs"])
    assert await _count(session) == len(GREENHOUSE_BOARD["jobs"])


async def test_a_success_records_when_the_board_last_worked(session: AsyncSession) -> None:
    """Separate from `last_fetched_at`, so a board failing daily cannot look healthy."""
    board = await _board(session)

    async with _client(_ok) as client:
        await ingest_board(session, board, client=client)

    assert board.last_succeeded_at is not None
    assert board.last_fetched_at is not None
    assert board.consecutive_failures == 0


# --- the unhappy paths, shipped with the adapter that handles them ---------------------


@pytest.mark.parametrize(
    ("name", "handler"),
    [
        ("server error", lambda _: httpx.Response(500, text="boom")),
        ("board gone", lambda _: httpx.Response(404, text="not found")),
        ("malformed body", lambda _: httpx.Response(200, text="<html>nope</html>")),
    ],
)
async def test_a_provider_failure_is_reported_not_raised(
    session: AsyncSession, name: str, handler: object
) -> None:
    """One dead company must not take down a refresh with thirty boards left to visit.

    So failure is a returned value rather than an exception, and the board carries the news
    in its own columns.
    """
    board = await _board(session)

    async with _client(handler) as client:
        result = await ingest_board(session, board, client=client)

    assert result.succeeded is False, name
    assert result.error
    assert board.consecutive_failures == 1
    assert board.last_error
    assert board.last_succeeded_at is None


async def test_a_timeout_is_reported_not_raised(session: AsyncSession) -> None:
    board = await _board(session)

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    async with _client(timeout) as client:
        result = await ingest_board(session, board, client=client)

    assert result.succeeded is False
    assert board.consecutive_failures == 1


async def test_a_failure_does_not_touch_the_jobs_already_stored(
    session: AsyncSession,
) -> None:
    """The guard ticket 05 depends on.

    If a failed fetch could empty or alter the index, an outage would look exactly like
    every job at a company closing at once.
    """
    board = await _board(session)
    async with _client(_ok) as client:
        await ingest_board(session, board, client=client)
    before = await _count(session)

    async with _client(lambda _: httpx.Response(503, text="down")) as client:
        await ingest_board(session, board, client=client)

    assert await _count(session) == before
    assert before > 0


async def test_repeated_failures_accumulate(session: AsyncSession) -> None:
    """Backoff in ticket 07 reads this counter, so it has to actually count."""
    board = await _board(session)

    async with _client(lambda _: httpx.Response(500)) as client:
        await ingest_board(session, board, client=client)
        await ingest_board(session, board, client=client)
        await ingest_board(session, board, client=client)

    assert board.consecutive_failures == 3


async def test_a_success_clears_a_previous_failure(session: AsyncSession) -> None:
    board = await _board(session)

    async with _client(lambda _: httpx.Response(500)) as client:
        await ingest_board(session, board, client=client)
    assert board.consecutive_failures == 1

    async with _client(_ok) as client:
        await ingest_board(session, board, client=client)

    assert board.consecutive_failures == 0
    assert board.last_error is None


async def test_an_empty_board_succeeds_with_nothing_created(session: AsyncSession) -> None:
    """A company with nothing open is normal, and must not look like a failure.

    Ticket 05 turns this into a rule: an empty response is not evidence that every job at a
    company closed, so the two cases must be distinguishable here.
    """
    board = await _board(session)

    async with _client(lambda _: httpx.Response(200, json={"jobs": []})) as client:
        result = await ingest_board(session, board, client=client)

    assert result.succeeded is True
    assert result.created == 0
    assert board.last_succeeded_at is not None


async def test_an_extremely_long_location_does_not_break_ingestion(
    session: AsyncSession,
) -> None:
    """A real Muse posting listed in dozens of cities produced 820 characters of location.

    Against a `varchar(500)` column that is a 500 from the refresh endpoint, and it took down
    the whole run rather than one posting. Provider-supplied display text has no length we get
    to assume, and story 21 says it is shown as written — so truncating would lose what the
    student reads, and the column has to hold it.
    """
    board = await _board(session)
    long_location = ", ".join(f"City {i}, ST" for i in range(120))
    assert len(long_location) > 1000

    payload = {
        "jobs": [
            {
                "id": 1,
                "title": "Field Technician",
                "absolute_url": "https://example.com/1",
                "content": "Work everywhere.",
                "location": {"name": long_location},
            }
        ]
    }

    async with _client(lambda _: httpx.Response(200, json=payload)) as client:
        result = await ingest_board(session, board, client=client)

    assert result.succeeded is True
    assert result.created == 1
    stored = (await session.execute(select(Job))).scalar_one()
    assert stored.location_raw == long_location, "kept whole, not truncated"


async def test_an_extremely_long_title_does_not_break_ingestion(
    session: AsyncSession,
) -> None:
    board = await _board(session)
    long_title = "Senior " * 200 + "Engineer"

    payload = {
        "jobs": [
            {
                "id": 2,
                "title": long_title,
                "absolute_url": "https://example.com/2",
                "content": "Text.",
            }
        ]
    }

    async with _client(lambda _: httpx.Response(200, json=payload)) as client:
        result = await ingest_board(session, board, client=client)

    assert result.succeeded is True
    assert result.created == 1


# --- a whole refresh ------------------------------------------------------------------


async def test_a_provider_with_no_adapter_yet_does_not_break_the_refresh(
    session: AsyncSession,
) -> None:
    """The registry is seeded with providers whose adapters arrive in ticket 03.

    Reaching one must not end the run. This is the isolation promise the entire refresh
    design rests on, and it has to hold for "not built yet" exactly as it does for a 500 —
    the first version of this raised KeyError and took down every board queued behind it.
    """
    session.add(BoardToken(provider="greenhouse", token="figma", company_name="Figma"))
    session.add(BoardToken(provider="workday", token="acme", company_name="Acme"))
    session.add(BoardToken(provider="smartrecruiters", token="beta", company_name="Beta"))
    await session.commit()

    async with _client(_ok) as client:
        summary = await refresh_all_boards(session, client=client)

    assert summary.boards_succeeded == 1
    assert summary.boards_skipped == 2
    assert summary.boards_failed == 0, "unsupported is not the same as broken"
    assert summary.created == len(GREENHOUSE_BOARD["jobs"])


async def test_an_unsupported_provider_is_not_recorded_as_failing(
    session: AsyncSession,
) -> None:
    """Story 28 depends on the failure count meaning something.

    A board we have not attempted is not a board that is broken, and counting it as broken
    would make the ledger cry wolf on every screen.
    """
    board = BoardToken(provider="workday", token="acme", company_name="Acme")
    session.add(board)
    await session.commit()

    async with _client(_ok) as client:
        await refresh_all_boards(session, client=client)

    assert board.consecutive_failures == 0
    assert board.last_error is None


async def test_one_failing_board_does_not_stop_the_others(session: AsyncSession) -> None:
    """A Lever outage must not cost us Greenhouse, Ashby and The Muse as well."""
    session.add(BoardToken(provider="greenhouse", token="good", company_name="Good"))
    session.add(BoardToken(provider="greenhouse", token="bad", company_name="Bad"))
    await session.commit()

    def selective(request: httpx.Request) -> httpx.Response:
        if "bad" in str(request.url):
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=GREENHOUSE_BOARD)

    async with _client(selective) as client:
        summary = await refresh_all_boards(session, client=client)

    assert summary.boards_attempted == 2
    assert summary.boards_succeeded == 1
    assert summary.boards_failed == 1
    assert summary.created == len(GREENHOUSE_BOARD["jobs"])


async def test_an_inactive_board_is_not_fetched(session: AsyncSession) -> None:
    board = BoardToken(
        provider="greenhouse", token="figma", company_name="Figma", active=False
    )
    session.add(board)
    await session.commit()

    async with _client(_ok) as client:
        summary = await refresh_all_boards(session, client=client)

    assert summary.boards_attempted == 0
    assert await _count(session) == 0
