"""Seeding the board registry.

The interesting property is not that seeding works but that it is safe to repeat, since it
runs on every container start alongside the demo student seed.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board_token import BoardToken
from app.seed_boards import SEED_BOARDS, seed_boards

pytestmark = pytest.mark.anyio


async def test_seeding_registers_the_curated_boards(session: AsyncSession) -> None:
    result = await seed_boards(session)

    assert result.created == len(SEED_BOARDS)
    count = (await session.execute(select(func.count()).select_from(BoardToken))).scalar_one()
    assert count == len(SEED_BOARDS)


async def test_seeding_twice_creates_no_duplicates(session: AsyncSession) -> None:
    """It runs on every container start, so this is the normal case, not an edge case."""
    await seed_boards(session)
    second = await seed_boards(session)

    assert second.created == 0
    assert second.already_present == len(SEED_BOARDS)
    count = (await session.execute(select(func.count()).select_from(BoardToken))).scalar_one()
    assert count == len(SEED_BOARDS)


async def test_seeding_does_not_reset_failure_history(session: AsyncSession) -> None:
    """Backoff would never engage if a deploy wiped the counters.

    A board dead for a week must stay backed off across restarts, or every deploy restarts
    the retry cycle for every dead board at full rate.
    """
    await seed_boards(session)
    board = (await session.execute(select(BoardToken))).scalars().first()
    assert board is not None
    board.consecutive_failures = 7
    board.last_error = "connect timeout"
    await session.commit()

    await seed_boards(session)

    reloaded = (
        await session.execute(select(BoardToken).where(BoardToken.id == board.id))
    ).scalar_one()
    assert reloaded.consecutive_failures == 7
    assert reloaded.last_error == "connect timeout"


async def test_seeding_does_not_reactivate_a_disabled_board(session: AsyncSession) -> None:
    """Switching a board off is a decision, and a deploy must not silently undo it."""
    await seed_boards(session)
    board = (await session.execute(select(BoardToken))).scalars().first()
    assert board is not None
    board.active = False
    await session.commit()

    await seed_boards(session)

    reloaded = (
        await session.execute(select(BoardToken).where(BoardToken.id == board.id))
    ).scalar_one()
    assert reloaded.active is False


async def test_every_seeded_board_names_a_known_provider() -> None:
    """A typo in a provider name would produce a row nothing ever fetches."""
    assert {board.provider for board in SEED_BOARDS} <= {"greenhouse", "lever", "ashby"}


async def test_no_seeded_board_is_listed_twice() -> None:
    pairs = [(board.provider, board.token) for board in SEED_BOARDS]

    assert len(pairs) == len(set(pairs))


async def test_the_muse_is_not_registered_as_a_board() -> None:
    """The Muse is one endpoint for every company, not one board per company.

    Registering it here would imply a per-company token that does not exist, and would put
    an aggregator in a table whose rows are treated as authoritative for closure.
    """
    assert not any(board.provider == "muse" for board in SEED_BOARDS)
