"""Dead postings leaving the feed.

This is the rule that separates Reachly from the aggregators it replaces. Applying to a role
that closed weeks ago is the most demoralising way to waste an evening, and no aggregator
prevents it because none can tell the difference between a job being gone and their own crawler
having a bad day.

Every test here is a way to destroy the index. The dangerous direction is not failing to close a
dead job — that is one wasted application. It is closing live ones: a sweep that misreads an
outage as mass closure empties the feed, and an empty feed is indistinguishable from a broken
product.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board_token import BoardToken
from app.models.job import Job
from app.services.ingest_service import (
    expire_stale_aggregator_rows,
    ingest_board,
    refresh_all_boards,
)

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
                "first_published": "2026-08-01T00:00:00Z",
            }
            for job_id in ids
        ]
    }


def _responds(payload: object) -> object:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


async def _board(
    session: AsyncSession,
    token: str = "figma",  # noqa: S107 - a board slug, not a credential
    company: str = "Figma",
) -> BoardToken:
    board = BoardToken(provider="greenhouse", token=token, company_name=company)
    session.add(board)
    await session.commit()
    return board


async def _job(session: AsyncSession, source_job_id: str) -> Job:
    return (
        await session.execute(select(Job).where(Job.source_job_id == source_job_id))
    ).scalar_one()


# --- the sweep itself -----------------------------------------------------------------


async def test_a_posting_absent_from_a_successful_fetch_is_closed(
    session: AsyncSession,
) -> None:
    board = await _board(session)

    async with _client(_responds(_payload(1, 2, 3))) as client:
        await ingest_board(session, board, client=client)

    async with _client(_responds(_payload(1, 3))) as client:
        result = await ingest_board(session, board, client=client)

    assert result.closed == 1, "job 2 stopped being listed"
    assert (await _job(session, "2")).closed_at is not None
    assert (await _job(session, "1")).closed_at is None
    assert (await _job(session, "3")).closed_at is None


async def test_a_failed_fetch_closes_nothing(session: AsyncSession) -> None:
    """The guard that matters most.

    A 500, a timeout or a connection error is not evidence about any job. Treating an outage as
    mass closure empties the feed, and a student cannot tell an empty feed from a broken app.
    """
    board = await _board(session)

    async with _client(_responds(_payload(1, 2, 3))) as client:
        await ingest_board(session, board, client=client)

    def broken(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream is having a bad day")

    async with _client(broken) as client:
        result = await ingest_board(session, board, client=client)

    assert result.succeeded is False
    assert result.closed == 0
    still_open = (
        await session.execute(select(Job).where(Job.closed_at.is_(None)))
    ).scalars().all()
    assert len(still_open) == 3, "an outage is not a closure"


async def test_a_connection_error_closes_nothing(session: AsyncSession) -> None:
    board = await _board(session)

    async with _client(_responds(_payload(1, 2))) as client:
        await ingest_board(session, board, client=client)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with _client(refused) as client:
        result = await ingest_board(session, board, client=client)

    assert result.succeeded is False
    assert result.closed == 0
    assert (await _job(session, "1")).closed_at is None


async def test_an_empty_response_where_there_were_many_closes_nothing(
    session: AsyncSession,
) -> None:
    """Far more likely a changed API shape or a revoked token than every role being filled.

    A 200 with an empty list is the shape a provider returns when a board is deleted, when a
    token is rotated, and when an adapter stops matching the payload. Trusting it would close a
    company's entire listing on the strength of the least reliable possible signal.
    """
    board = await _board(session)

    async with _client(_responds(_payload(1, 2, 3))) as client:
        await ingest_board(session, board, client=client)

    async with _client(_responds({"jobs": []})) as client:
        result = await ingest_board(session, board, client=client)

    assert result.closed == 0
    assert result.suspicious is True, "recorded, not silently ignored"
    open_rows = (
        await session.execute(select(Job).where(Job.closed_at.is_(None)))
    ).scalars().all()
    assert len(open_rows) == 3


async def test_an_empty_response_from_a_board_that_was_always_empty_is_not_suspicious(
    session: AsyncSession,
) -> None:
    """A company with no openings is normal, and must not be flagged forever."""
    board = await _board(session)

    async with _client(_responds({"jobs": []})) as client:
        result = await ingest_board(session, board, client=client)

    assert result.succeeded is True
    assert result.suspicious is False
    assert result.closed == 0


async def test_one_board_never_closes_another_boards_jobs(session: AsyncSession) -> None:
    """Two boards on the same provider, which is the case that makes this non-trivial.

    Sweeping by `source` alone would have Figma's refresh close Linear's entire listing, since
    both are Greenhouse and neither appears in the other's response.
    """
    figma = await _board(session, token="figma", company="Figma")
    linear = await _board(session, token="linear", company="Linear")

    async with _client(_responds(_payload(1, 2))) as client:
        await ingest_board(session, figma, client=client)
    async with _client(_responds(_payload(10, 11))) as client:
        await ingest_board(session, linear, client=client)

    # Figma now lists only job 1. Linear is not refreshed at all.
    async with _client(_responds(_payload(1))) as client:
        result = await ingest_board(session, figma, client=client)

    assert result.closed == 1
    linear_rows = (
        await session.execute(select(Job).where(Job.company_name == "Linear"))
    ).scalars().all()
    assert all(row.closed_at is None for row in linear_rows), "not Figma's business"


async def test_two_boards_sharing_a_company_name_do_not_close_each_other(
    session: AsyncSession,
) -> None:
    """Scoping the sweep by company name would be wrong for a company with two boards.

    A firm running a separate board for a region or a subsidiary is common, and both would carry
    the same `company_name`.
    """
    main = await _board(session, token="stripe", company="Stripe")
    eu = await _board(session, token="stripe-eu", company="Stripe")

    async with _client(_responds(_payload(1))) as client:
        await ingest_board(session, main, client=client)
    async with _client(_responds(_payload(2))) as client:
        await ingest_board(session, eu, client=client)

    async with _client(_responds(_payload(1))) as client:
        result = await ingest_board(session, main, client=client)

    assert result.closed == 0
    assert (await _job(session, "2")).closed_at is None


# --- what closure means for the record ------------------------------------------------


async def test_a_closed_job_is_still_retrievable_by_id(session: AsyncSession) -> None:
    """History cannot develop holes. A student applied to this, and deserves an answer."""
    from app.services.job_service import get_job

    board = await _board(session)
    async with _client(_responds(_payload(1))) as client:
        await ingest_board(session, board, client=client)
    stored_id = (await _job(session, "1")).id

    other = {
        "jobs": [
            {
                "id": 99,
                "title": "Other",
                "absolute_url": "https://e.com/99",
                "content": "x",
            }
        ]
    }
    async with _client(_responds(other)) as client:
        await ingest_board(session, board, client=client)

    assert (await _job(session, "1")).closed_at is not None
    fetched = await get_job(session, stored_id)
    assert fetched.id == stored_id, "still resolves"


async def test_a_closed_job_is_excluded_from_the_feed_by_default(
    session: AsyncSession,
) -> None:
    from app.services.job_service import JobFilters, list_jobs

    board = await _board(session)
    async with _client(_responds(_payload(1, 2))) as client:
        await ingest_board(session, board, client=client)
    async with _client(_responds(_payload(1))) as client:
        await ingest_board(session, board, client=client)

    default_page = await list_jobs(session)
    assert [job.source_job_id for job in default_page.items] == ["1"]

    with_closed = await list_jobs(session, filters=JobFilters(include_closed=True))
    assert {job.source_job_id for job in with_closed.items} == {"1", "2"}


async def test_a_reappearing_job_is_reopened_rather_than_duplicated(
    session: AsyncSession,
) -> None:
    """Roles are reposted, and a second row would defeat ticket 06 before it starts."""
    board = await _board(session)

    async with _client(_responds(_payload(1, 2))) as client:
        await ingest_board(session, board, client=client)
    async with _client(_responds(_payload(1))) as client:
        await ingest_board(session, board, client=client)
    assert (await _job(session, "2")).closed_at is not None

    async with _client(_responds(_payload(1, 2))) as client:
        result = await ingest_board(session, board, client=client)

    assert result.reopened == 1
    assert result.created == 0, "reopened, not created again"
    rows = (
        await session.execute(select(Job).where(Job.source_job_id == "2"))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].closed_at is None


async def test_closed_at_records_first_absence_not_the_latest_sweep(
    session: AsyncSession,
) -> None:
    """Otherwise every sweep moves the date forward and the job looks freshly closed forever.

    A student looking at a role closed three weeks ago should see three weeks ago.
    """
    board = await _board(session)

    async with _client(_responds(_payload(1, 2))) as client:
        await ingest_board(session, board, client=client)
    async with _client(_responds(_payload(1))) as client:
        await ingest_board(session, board, client=client)

    first_observation = (await _job(session, "2")).closed_at
    assert first_observation is not None

    async with _client(_responds(_payload(1))) as client:
        result = await ingest_board(session, board, client=client)

    assert result.closed == 0, "already closed, not closed again"
    assert (await _job(session, "2")).closed_at == first_observation


# --- the aggregator, which absence tells us nothing about -----------------------------


async def test_aggregator_rows_expire_on_a_timer_rather_than_being_swept(
    session: AsyncSession,
) -> None:
    """The Muse does not enumerate a complete set, so absence proves nothing about it.

    A Muse posting missing from page three today may simply have moved to page four. Sweeping it
    the way a board is swept would close live jobs on no evidence at all.
    """
    fresh = Job(
        source="muse",
        source_job_id="fresh",
        company_name="Acme",
        title="Junior Developer",
        description="x",
        apply_url="https://example.com/fresh",
        is_verified=False,
    )
    stale = Job(
        source="muse",
        source_job_id="stale",
        company_name="Acme",
        title="Junior Analyst",
        description="x",
        apply_url="https://example.com/stale",
        is_verified=False,
        last_seen_at=datetime.now(UTC) - timedelta(days=20),
    )
    verified_and_old = Job(
        source="greenhouse",
        source_job_id="board-old",
        company_name="Acme",
        title="Engineer",
        description="x",
        apply_url="https://example.com/board",
        is_verified=True,
        last_seen_at=datetime.now(UTC) - timedelta(days=20),
    )
    session.add_all([fresh, stale, verified_and_old])
    await session.commit()

    expired = await expire_stale_aggregator_rows(session, max_age_days=14)

    assert expired == 1
    assert (await _job(session, "stale")).closed_at is not None
    assert (await _job(session, "fresh")).closed_at is None
    assert (await _job(session, "board-old")).closed_at is None, (
        "a board row is swept by absence, never by age — a genuinely old posting is still open"
    )


# --- visibility ------------------------------------------------------------------------


async def test_closure_counts_are_reported_per_source(session: AsyncSession) -> None:
    """A rule change that starts closing everything must be visible before the feed empties."""
    board = await _board(session)

    async with _client(_responds(_payload(1, 2, 3))) as client:
        await ingest_board(session, board, client=client)

    async with _client(_responds(_payload(1))) as client:
        summary = await refresh_all_boards(session, client=client)

    assert summary.closed == 2
    assert summary.closed_by_source["greenhouse"] == 2
