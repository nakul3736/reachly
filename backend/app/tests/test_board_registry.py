"""The board registry, and the constraints that make ingestion safe.

Spike 001 is why this table exists rather than a list of company names transformed into
URLs at runtime: 12 of 20 plausible Lever slugs returned 404, so the tokens are not
derivable and have to be stored.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board_token import BoardToken
from app.models.job import DedupVerdict, Job

pytestmark = pytest.mark.anyio


def _board(**overrides: object) -> BoardToken:
    values: dict[str, object] = {
        "provider": "greenhouse",
        "token": "example",
        "company_name": "Example",
    }
    values.update(overrides)
    return BoardToken(**values)


def _job(**overrides: object) -> Job:
    values: dict[str, object] = {
        "source": "greenhouse",
        "source_job_id": "1",
        "company_name": "Example",
        "title": "Software Engineer",
        "location_raw": "Toronto, Ontario, Canada",
        "description": "Build things.",
        "apply_url": "https://example.com/1",
        "is_verified": True,
    }
    values.update(overrides)
    return Job(**values)


# --- board_token ----------------------------------------------------------------------


async def test_a_board_can_be_registered(session: AsyncSession) -> None:
    session.add(_board())
    await session.commit()

    stored = (await session.execute(select(BoardToken))).scalar_one()

    assert stored.provider == "greenhouse"
    assert stored.token == "example"
    assert stored.active is True
    assert stored.consecutive_failures == 0
    assert stored.last_succeeded_at is None


async def test_the_same_board_cannot_be_registered_twice(session: AsyncSession) -> None:
    """A constraint, not a check-then-insert.

    Two refreshes racing would both pass a check. The same reasoning as duplicate email
    registration in feature 01.
    """
    session.add(_board())
    await session.commit()

    session.add(_board(company_name="Example Renamed"))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_one_token_can_exist_on_two_providers(session: AsyncSession) -> None:
    """Uniqueness is on the pair.

    `stripe` is a plausible slug on more than one provider, and they are different boards.
    """
    session.add(_board(provider="greenhouse", token="acme"))
    session.add(_board(provider="lever", token="acme"))
    await session.commit()

    assert len((await session.execute(select(BoardToken))).scalars().all()) == 2


# --- job ------------------------------------------------------------------------------


async def test_a_job_can_be_stored(session: AsyncSession) -> None:
    session.add(_job())
    await session.commit()

    stored = (await session.execute(select(Job))).scalar_one()

    assert stored.title == "Software Engineer"
    assert stored.closed_at is None
    assert stored.canonical_job_id is None
    assert stored.first_seen_at is not None


async def test_the_same_posting_cannot_be_stored_twice(session: AsyncSession) -> None:
    """The constraint that makes ingestion idempotent.

    Without it, a refresh re-run after a crash doubles every job in the index.
    """
    session.add(_job(source="greenhouse", source_job_id="42"))
    await session.commit()

    session.add(_job(source="greenhouse", source_job_id="42", title="Changed"))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_two_sources_may_carry_the_same_job_id(session: AsyncSession) -> None:
    """Provider ids are not globally unique, which is why identity is fingerprinted.

    Greenhouse job 42 and Muse job 42 are unrelated. Collapsing them is ticket 06's
    problem and must be decided on content, not on a coincidence of numbering.
    """
    session.add(_job(source="greenhouse", source_job_id="42"))
    session.add(_job(source="muse", source_job_id="42", is_verified=False))
    await session.commit()

    assert len((await session.execute(select(Job))).scalars().all()) == 2


async def test_timestamps_are_timezone_aware_and_utc(session: AsyncSession) -> None:
    session.add(_job())
    await session.commit()

    stored = (await session.execute(select(Job))).scalar_one()

    assert stored.first_seen_at.tzinfo is not None
    assert stored.first_seen_at.utcoffset() == timedelta(0)


async def test_a_job_can_be_marked_closed(session: AsyncSession) -> None:
    """Closed, not deleted — a student's application must still resolve to it."""
    session.add(_job())
    await session.commit()

    stored = (await session.execute(select(Job))).scalar_one()
    stored.closed_at = datetime.now(UTC)
    await session.commit()

    reloaded = (await session.execute(select(Job))).scalar_one()
    assert reloaded.closed_at is not None


# --- dedup_verdict --------------------------------------------------------------------


async def test_a_verdict_can_be_cached(session: AsyncSession) -> None:
    session.add(
        DedupVerdict(
            fingerprint_low="aaa", fingerprint_high="bbb", same_job=True, decided_by="fuzzy"
        )
    )
    await session.commit()

    stored = (await session.execute(select(DedupVerdict))).scalar_one()

    assert stored.same_job is True
    assert stored.decided_by == "fuzzy"


async def test_the_same_pair_cannot_be_cached_twice(session: AsyncSession) -> None:
    """The pair is stored sorted, so one comparison cannot be paid for twice.

    The columns are named low and high rather than a and b precisely so that this cannot
    be got wrong by a caller passing them the other way round.
    """
    session.add(
        DedupVerdict(
            fingerprint_low="aaa", fingerprint_high="bbb", same_job=True, decided_by="fuzzy"
        )
    )
    await session.commit()

    session.add(
        DedupVerdict(
            fingerprint_low="aaa",
            fingerprint_high="bbb",
            same_job=False,
            decided_by="inference",
        )
    )

    with pytest.raises(IntegrityError):
        await session.commit()


# --- the sources endpoint -------------------------------------------------------------


async def test_sources_lists_registered_boards(
    client: AsyncClient, session: AsyncSession
) -> None:
    session.add(_board(provider="greenhouse", token="acme", company_name="Acme"))
    session.add(_board(provider="ashby", token="beta", company_name="Beta"))
    await session.commit()

    response = await client.get("/api/v1/sources")

    assert response.status_code == 200
    companies = {item["company_name"] for item in response.json()["boards"]}
    assert companies == {"Acme", "Beta"}


async def test_sources_needs_no_account(client: AsyncClient, session: AsyncSession) -> None:
    """Story 1 is the first thing a visitor should be able to do.

    Requiring registration to find out whether the product has any jobs in it is the
    reason people leave.
    """
    session.add(_board())
    await session.commit()

    response = await client.get("/api/v1/sources")

    assert response.status_code == 200


async def test_sources_reports_failure_state(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Story 28 — a silently broken adapter should be visible, not merely quiet."""
    session.add(_board(consecutive_failures=3, last_error="timeout"))
    await session.commit()

    board = response_board(await client.get("/api/v1/sources"))

    assert board["consecutive_failures"] == 3
    assert board["last_error"] == "timeout"
    assert board["last_succeeded_at"] is None


def response_board(response: object) -> dict[str, object]:
    payload = response.json()  # type: ignore[attr-defined]
    boards: list[dict[str, object]] = payload["boards"]
    assert len(boards) == 1
    return boards[0]
