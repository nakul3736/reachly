"""The refresh that maintains the index without anyone watching it.

The properties here are all about a run that nobody is supervising: one dead company must not
cost
the other seventeen, a permanently dead company must not consume the window every day forever, a
run must not exceed the time its host will give it, and running twice must not double anything.

ADR 0007 put the trigger outside the process. An in-process timer stops silently on a host that
suspends idle containers, and silence is the failure mode that costs a judged
window.
"""

import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board_token import BoardToken
from app.models.job import Job
from app.services.ingest_service import refresh_all_boards, should_attempt

pytestmark = pytest.mark.anyio


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _payload(*ids: int) -> dict[str, object]:
    return {
        "jobs": [
            {
                "id": job_id,
                "title": f"Engineer {job_id}",
                "absolute_url": f"https://example.com/{job_id}",
                "content": "Build things.",
                "location": {"name": "Toronto, ON, Canada"},
            }
            for job_id in ids
        ]
    }


def _ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_payload(1, 2))


def _ok_per_board(request: httpx.Request) -> httpx.Response:
    """Distinct ids per board, because `jobs` is unique on `(source, source_job_id)`.

    That constraint assumes a provider's ids are unique across its boards, which holds for all
    four sources here — Greenhouse issues them from one sequence, Lever and Ashby use UUIDs, and
    The Muse has a single id space. A fixture that reused ids across boards would collide in a
    way
    no real provider does, and would test the constraint rather than the refresh.
    """
    found = re.search(r"/boards/([^/?]+)", str(request.url))
    token = found.group(1) if found else "unknown"
    base = (abs(hash(token)) % 1000) * 100
    return httpx.Response(200, json=_payload(base + 1, base + 2))


def _dead(_: httpx.Request) -> httpx.Response:
    return httpx.Response(404, text="no such board")


async def _boards(session: AsyncSession, count: int = 3) -> list[BoardToken]:
    boards = [
        BoardToken(provider="greenhouse", token=f"board{i}", company_name=f"Company {i}")
        for i in range(count)
    ]
    session.add_all(boards)
    await session.commit()
    return boards


# --- backoff ---------------------------------------------------------------------------


def test_a_healthy_board_is_always_attempted() -> None:
    board = BoardToken(provider="greenhouse", token="figma", company_name="Figma")
    board.consecutive_failures = 0
    board.last_fetched_at = datetime.now(UTC)
    assert should_attempt(board) is True


def test_a_board_that_just_failed_once_is_retried_promptly() -> None:
    """One failure is noise. Providers return the occasional 500 and recover in a minute."""
    board = BoardToken(provider="greenhouse", token="figma", company_name="Figma")
    board.consecutive_failures = 1
    board.last_fetched_at = datetime.now(UTC) - timedelta(hours=2)
    assert should_attempt(board) is True


def test_a_repeatedly_failing_board_is_skipped_until_its_delay_has_passed() -> None:
    """A company that deleted its board should not be asked every day forever.

    The run window on a free host is finite, and eighteen boards share it. A permanently dead
    board that keeps its full share is taking time from boards that still work.
    """
    board = BoardToken(provider="greenhouse", token="gone", company_name="Gone")
    board.consecutive_failures = 6
    board.last_fetched_at = datetime.now(UTC) - timedelta(minutes=30)
    assert should_attempt(board) is False


def test_a_backed_off_board_is_eventually_tried_again() -> None:
    """Never permanently. A board can come back, and only an attempt can discover that.

    This is why backoff is a delay rather than deactivation: nothing in the system would ever
    reactivate a board it had given up on.
    """
    board = BoardToken(provider="greenhouse", token="gone", company_name="Gone")
    board.consecutive_failures = 6
    board.last_fetched_at = datetime.now(UTC) - timedelta(days=30)
    assert should_attempt(board) is True


def test_the_backoff_delay_is_capped() -> None:
    """Otherwise doubling reaches decades and the board is dead forever in practice."""
    board = BoardToken(provider="greenhouse", token="gone", company_name="Gone")
    board.consecutive_failures = 400
    board.last_fetched_at = datetime.now(UTC) - timedelta(days=4)
    assert should_attempt(board) is True


def test_a_board_never_fetched_is_attempted_regardless_of_its_counters() -> None:
    board = BoardToken(provider="greenhouse", token="new", company_name="New")
    board.consecutive_failures = 9
    board.last_fetched_at = None
    assert should_attempt(board) is True


async def test_backed_off_boards_are_reported_and_do_not_count_as_failures(
    session: AsyncSession,
) -> None:
    """A board nobody asked is not a board that broke, and the counts must not conflate them."""
    boards = await _boards(session, 2)
    boards[0].consecutive_failures = 8
    boards[0].last_fetched_at = datetime.now(UTC) - timedelta(minutes=10)
    await session.commit()

    async with _client(_ok) as client:
        summary = await refresh_all_boards(session, client=client)

    assert summary.boards_backed_off == 1
    assert summary.boards_failed == 0
    assert summary.boards_attempted == 1
    assert summary.boards_succeeded == 1


# --- failure counters ------------------------------------------------------------------


async def test_a_failure_records_itself_and_a_success_clears_it(
    session: AsyncSession,
) -> None:
    board = (await _boards(session, 1))[0]

    async with _client(_dead) as client:
        await refresh_all_boards(session, client=client)

    await session.refresh(board)
    assert board.consecutive_failures == 1
    assert board.last_error is not None

    async with _client(_ok) as client:
        await refresh_all_boards(session, client=client)

    await session.refresh(board)
    assert board.consecutive_failures == 0
    assert board.last_error is None
    assert board.last_succeeded_at is not None


async def test_one_failing_board_does_not_cost_the_others(session: AsyncSession) -> None:
    """A Lever outage must not lose us Greenhouse, Ashby and The Muse."""
    boards = await _boards(session, 3)

    def selective(request: httpx.Request) -> httpx.Response:
        if boards[1].token in str(request.url):
            return httpx.Response(500, text="broken")
        return httpx.Response(200, json=_payload(1, 2))

    async with _client(selective) as client:
        summary = await refresh_all_boards(session, client=client)

    assert summary.boards_attempted == 3
    assert summary.boards_succeeded == 2
    assert summary.boards_failed == 1
    assert summary.created > 0, "the working boards still landed"


# --- a bounded run ---------------------------------------------------------------------


async def test_the_run_stops_starting_boards_once_its_deadline_passes(
    session: AsyncSession,
) -> None:
    """The host will kill a request that runs too long, and a killed run reports nothing.

    Stopping early with a truthful summary is strictly better: the boards not reached are still
    active and the next trigger begins with them, because ordering puts the least recently
    fetched first.
    """
    await _boards(session, 5)

    async with _client(_ok) as client:
        summary = await refresh_all_boards(
            session, client=client, max_seconds=0.0
        )

    assert summary.deadline_reached is True
    assert summary.boards_attempted < 5


async def test_a_bounded_run_leaves_the_index_consistent(session: AsyncSession) -> None:
    """A partial run is a smaller run, never a half-swept one.

    Closure is scoped to the board just fetched, so boards never reached in a truncated run keep
    every posting. The dangerous alternative — sweeping globally at the end of a run — would
    close the entire index whenever a run was cut short.
    """
    boards = await _boards(session, 3)

    async with _client(_ok_per_board) as client:
        await refresh_all_boards(session, client=client)

    total_before = len(
        (await session.execute(select(Job).where(Job.closed_at.is_(None)))).scalars().all()
    )
    assert total_before == 6

    async with _client(_ok_per_board) as client:
        await refresh_all_boards(session, client=client, max_seconds=0.0)

    still_open = len(
        (await session.execute(select(Job).where(Job.closed_at.is_(None)))).scalars().all()
    )
    assert still_open == total_before, "an unvisited board closes nothing"
    assert boards[0].active is True


# --- idempotency -----------------------------------------------------------------------


async def test_running_twice_creates_nothing_the_second_time(
    session: AsyncSession,
) -> None:
    await _boards(session, 2)

    async with _client(_ok_per_board) as client:
        first = await refresh_all_boards(session, client=client)
        second = await refresh_all_boards(session, client=client)

    assert first.created == 4
    assert second.created == 0
    assert second.updated == 4
    assert second.closed == 0, "nothing disappeared between two identical responses"
