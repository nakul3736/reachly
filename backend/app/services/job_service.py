"""Reading the shared job index.

Ordering is by recency until feature 03 brings scoring. Kept free of FastAPI.
"""

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import JobNotFound
from app.models.job import Job


@dataclass
class JobPage:
    items: list[Job]
    total: int
    page: int
    page_size: int


def _visible() -> Select[tuple[Job]]:
    """The feed's baseline: open jobs that are not an alias of another row.

    Both conditions are exclusions rather than orderings. A closed job is not a worse
    opportunity, it is not an opportunity, and an alias is the same opportunity twice.
    """
    return select(Job).where(Job.closed_at.is_(None), Job.canonical_job_id.is_(None))


async def list_jobs(session: AsyncSession, *, page: int = 1, page_size: int = 20) -> JobPage:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    base = _visible()

    total = int(
        (
            await session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
    )

    # Newest first, by when the source says it was posted. `posted_at` is frequently absent,
    # so `first_seen_at` is the fallback rather than letting nulls sort arbitrarily — a job
    # with no date is not automatically the oldest thing in the index.
    ordered = base.order_by(
        func.coalesce(Job.posted_at, Job.first_seen_at).desc(), Job.id.desc()
    )

    rows = (
        await session.execute(ordered.offset((page - 1) * page_size).limit(page_size))
    ).scalars()

    return JobPage(items=list(rows), total=total, page=page, page_size=page_size)


async def get_job(session: AsyncSession, job_id: int) -> Job:
    """One job, closed or not.

    A closed job is returned rather than hidden. The student may have applied to it, and a
    404 would be a lie about something that existed.
    """
    job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise JobNotFound
    return job
