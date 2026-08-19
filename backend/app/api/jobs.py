"""The public job feed."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.domain.role_family import ROLE_FAMILIES, Seniority
from app.models.job import Job
from app.services import job_service
from app.services.job_service import JobFilters

router = APIRouter(prefix="/jobs", tags=["jobs"])

_SENIORITIES = {str(s) for s in Seniority}
_COUNTRIES = {"US", "CA"}


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

    # Whether the company's own board carries this posting. Not decoration: an aggregator copy
    # is a weaker claim, and the interface says which it is.
    is_verified: bool


class JobDetail(JobSummary):
    description: str
    apply_url: str


class JobFeed(BaseModel):
    items: list[JobSummary]
    total: int
    page: int
    page_size: int
    # Echoed back so an empty feed can name the filter responsible instead of only reporting
    # that nothing matched.
    applied_filters: dict[str, object]


def _csv(value: str | None, allowed: set[str], name: str) -> list[str]:
    """Parse a comma-separated filter, rejecting anything unrecognised.

    Rejected rather than ignored. Silently dropping an unknown value shows the student a feed
    they did not ask for, from which they would reasonably conclude the filter does nothing.
    """
    if not value:
        return []

    parts = [part.strip() for part in value.split(",") if part.strip()]
    unknown = [part for part in parts if part not in allowed]
    if unknown:
        raise HTTPException(
            # The spelling starlette now wants; the ENTITY name is deprecated and the
            # project treats DeprecationWarning as an error.
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Unknown {name}: {', '.join(unknown)}. "
                f"Choose from {', '.join(sorted(allowed))}."
            ),
        )
    return parts


@router.get("", response_model=JobFeed)
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    seniority: str | None = Query(None, description="Comma separated: entry, senior, unknown"),
    role_family: str | None = Query(None, description="Comma separated role families"),
    country: str | None = Query(None, description="Comma separated: US, CA"),
    remote: bool | None = Query(None),
    q: str | None = Query(None, max_length=200),
    company: str | None = Query(None, max_length=200),
    session: AsyncSession = Depends(get_session),
) -> JobFeed:
    filters = JobFilters(
        seniority=_csv(seniority, _SENIORITIES, "seniority"),
        role_family=_csv(role_family, set(ROLE_FAMILIES), "role_family"),
        country=_csv(country, _COUNTRIES, "country"),
        remote=remote,
        q=q.strip() if q and q.strip() else None,
        company=company.strip() if company and company.strip() else None,
    )

    result = await job_service.list_jobs(
        session, page=page, page_size=page_size, filters=filters
    )

    return JobFeed(
        items=[JobSummary.model_validate(j, from_attributes=True) for j in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        applied_filters=result.filters.as_dict(),
    )


@router.get("/meta/filters")
async def filter_options() -> dict[str, list[str]]:
    """What the feed can be filtered by.

    Served rather than duplicated in the frontend, so a family added to the classifier becomes
    selectable without a second edit in another language.
    """
    return {
        "role_family": list(ROLE_FAMILIES),
        "seniority": sorted(_SENIORITIES),
        "country": sorted(_COUNTRIES),
    }


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)) -> Job:
    return await job_service.get_job(session, job_id)
