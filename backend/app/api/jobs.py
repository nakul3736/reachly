"""The public job feed."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.job import Job
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobSummary(BaseModel):
    id: int
    source: str
    company_name: str
    title: str
    location_raw: str | None
    country: str | None
    is_remote: bool | None
    role_family: str | None
    seniority: str | None
    posted_at: datetime | None
    first_seen_at: datetime
    closed_at: datetime | None

    # Whether the company's own board carries this posting. Not decoration: an aggregator
    # copy is a weaker claim and the interface states which it is.
    is_verified: bool


class JobDetail(JobSummary):
    description: str
    apply_url: str


class JobFeed(BaseModel):
    items: list[JobSummary]
    total: int
    page: int
    page_size: int


@router.get("", response_model=JobFeed)
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> JobFeed:
    result = await job_service.list_jobs(session, page=page, page_size=page_size)
    return JobFeed(
        items=[JobSummary.model_validate(j, from_attributes=True) for j in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> Job:
    return await job_service.get_job(session, job_id)
