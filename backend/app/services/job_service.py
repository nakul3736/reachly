"""Reading and filtering the shared job index.

Ordering is by recency until feature 03 brings scoring. Kept free of FastAPI.
"""

from dataclasses import dataclass, field

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.location import extract_location
from app.domain.role_family import classify_role_family, classify_seniority
from app.errors import JobNotFound
from app.models.job import Job


@dataclass
class JobFilters:
    """What the student asked for.

    Lists rather than single values because the useful queries are unions. Explicit entry-level
    postings are rare — 14 of the 2,586 currently indexed — so a graduating student's real
    question is "not obviously too senior", which needs `entry` and `unknown` together.
    """

    seniority: list[str] = field(default_factory=list)
    role_family: list[str] = field(default_factory=list)
    country: list[str] = field(default_factory=list)
    remote: bool | None = None
    q: str | None = None
    company: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Echoed back so an empty result can name the filter responsible."""
        return {
            "seniority": self.seniority,
            "role_family": self.role_family,
            "country": self.country,
            "remote": self.remote,
            "q": self.q,
            "company": self.company,
        }


@dataclass
class JobPage:
    items: list[Job]
    total: int
    page: int
    page_size: int
    filters: JobFilters


def _visible() -> Select[tuple[Job]]:
    """The feed's baseline: open jobs that are not an alias of another row.

    Both are exclusions rather than orderings. A closed job is not a worse opportunity, it is
    not an opportunity, and an alias is the same opportunity twice.
    """
    return select(Job).where(Job.closed_at.is_(None), Job.canonical_job_id.is_(None))


def _apply(statement: Select[tuple[Job]], filters: JobFilters) -> Select[tuple[Job]]:
    """Every filter is an exclusion.

    ADR 0003 settled location as a hard filter, and seniority follows the same logic: a role
    wanting a decade of experience is not a weaker match for a graduating student, it is not a
    match. Ranking such a job lower would still put it on the screen.
    """
    if filters.seniority:
        statement = statement.where(Job.seniority.in_(filters.seniority))
    if filters.role_family:
        statement = statement.where(Job.role_family.in_(filters.role_family))
    if filters.country:
        statement = statement.where(Job.country.in_(filters.country))
    if filters.remote is not None:
        statement = statement.where(Job.is_remote.is_(filters.remote))
    if filters.company:
        statement = statement.where(Job.company_name.ilike(f"%{filters.company}%"))
    if filters.q:
        # Substring over title and description. BM25 arrives in feature 03 as a scoring
        # component, which is where relevance belongs — here the question is only whether a
        # posting mentions the thing at all.
        needle = f"%{filters.q}%"
        statement = statement.where(
            or_(Job.title.ilike(needle), Job.description.ilike(needle))
        )
    return statement


async def list_jobs(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    filters: JobFilters | None = None,
) -> JobPage:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    filters = filters or JobFilters()

    base = _apply(_visible(), filters)

    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )

    # Newest first by what the source says. `posted_at` is frequently absent, so `first_seen_at`
    # is the fallback rather than letting nulls sort arbitrarily — a posting with no date is not
    # automatically the oldest thing in the index.
    ordered = base.order_by(
        func.coalesce(Job.posted_at, Job.first_seen_at).desc(), Job.id.desc()
    )

    rows = (
        await session.execute(ordered.offset((page - 1) * page_size).limit(page_size))
    ).scalars()

    return JobPage(
        items=list(rows), total=total, page=page, page_size=page_size, filters=filters
    )


async def get_job(session: AsyncSession, job_id: int) -> Job:
    """One job, closed or not.

    A closed job is returned rather than hidden. The student may have applied to it, and a 404
    would be a lie about something that existed.
    """
    job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise JobNotFound
    return job


async def classify_stored_jobs(session: AsyncSession, *, force: bool = False) -> int:
    """Derive role family, seniority, country and remote for stored jobs.

    Runs over the index rather than during fetch, so a corrected rule can be applied to the
    2,586 postings already held without asking ten providers for them again. On a free host a
    full refresh is an hour, and a burst of requests we should not make to fix our own bug.

    Only unclassified rows are touched unless `force` is set, which keeps the common case cheap
    while still allowing a deliberate reclassification after a rule change.
    """
    statement = select(Job)
    if not force:
        statement = statement.where(Job.role_family.is_(None))

    jobs = (await session.execute(statement)).scalars().all()

    for job in jobs:
        location = extract_location(job.location_raw)
        job.role_family = classify_role_family(job.title)
        job.seniority = str(classify_seniority(job.title))
        # location_raw is never written back. Story 21: the derived country sits beside the
        # text as published, so a wrong guess stays visible.
        job.country = location.country
        job.is_remote = location.is_remote

    await session.commit()
    return len(jobs)
