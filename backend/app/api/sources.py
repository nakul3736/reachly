"""The board registry, readable without an account.

Public deliberately. Story 1 is the first thing a visitor should be able to do, and
requiring registration to find out whether the product has any real companies behind it is
the reason people leave.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services import source_service

router = APIRouter(prefix="/sources", tags=["sources"])


class BoardOut(BaseModel):
    provider: str
    token: str
    company_name: str
    active: bool
    last_fetched_at: datetime | None
    last_succeeded_at: datetime | None
    consecutive_failures: int
    last_error: str | None


class SourcesOut(BaseModel):
    boards: list[BoardOut]


@router.get("", response_model=SourcesOut)
async def list_sources(session: AsyncSession = Depends(get_session)) -> SourcesOut:
    boards = await source_service.list_boards(session)
    return SourcesOut(boards=[BoardOut.model_validate(b, from_attributes=True) for b in boards])
