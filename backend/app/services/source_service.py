"""Reading the board registry.

Kept free of FastAPI, per the layering rule that held through feature 01.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board_token import BoardToken


async def list_boards(session: AsyncSession) -> list[BoardToken]:
    """Every registered board, active first, then by company name.

    Ordered so the healthy majority does not bury a deactivated board at an arbitrary
    position, and stable so the response does not reshuffle between requests.
    """
    result = await session.execute(
        select(BoardToken).order_by(
            BoardToken.active.desc(), BoardToken.company_name, BoardToken.provider
        )
    )
    return list(result.scalars().all())
