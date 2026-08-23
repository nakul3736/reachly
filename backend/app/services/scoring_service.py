"""Computing and persisting match scores, lazily per page.

The key decision: scores are computed for the twenty postings a student is looking at, not for the
whole index at once. A full pass over 4,437 postings would be the most expensive operation in the
application, almost entirely for pages nobody scrolls to. Lazy means the first render of a page
pays the cost and every subsequent render reads from storage.

The resume version is part of the key. Uploading a new resume invalidates nothing — the old rows
simply stop matching the current key, and the next page render produces fresh ones.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.experience import parse_experience_requirement
from app.domain.scoring import MatchBreakdown, StudentProfile, score_job
from app.domain.skill_extraction import extract_skills, normalise_skill_list
from app.models.job import Job
from app.models.match_score import MatchScore
from app.models.resume import ResumeMaster


async def get_student_profile(session: AsyncSession, student_id: int) -> StudentProfile | None:
    """Build a profile from the active resume, or None if there is no active resume.

    None is a real answer: story 34 says a student with no resume sees the feed ordered by
    recency, and the score area explains what uploading would add.
    """
    stmt = select(ResumeMaster).where(
        ResumeMaster.student_id == student_id,
        ResumeMaster.is_active.is_(True),
    )
    resume = (await session.execute(stmt)).scalars().first()
    if resume is None or resume.parsed_json is None:
        return None

    from typing import cast

    raw_skills = cast(list[str], resume.parsed_json.get("skills") or [])
    skills = normalise_skill_list(raw_skills)

    # Years of experience from the resume's experience entries. A rough sum of tenures rather
    # than a precise calculation — what matters for scoring is the order of magnitude, not the
    # month count.
    years = 0.0
    experience_entries = cast(
        list[dict[str, object]], resume.parsed_json.get("experience") or []
    )
    for entry in experience_entries:
        dates = str(entry.get("dates", ""))
        if "present" in dates.lower() or "current" in dates.lower():
            years += 1.0
        elif dates:
            years += 0.5

    raw_text = str(resume.parsed_json.get("raw_text", ""))
    return StudentProfile(skills=skills, years_experience=years, resume_text=raw_text)


async def score_page(
    session: AsyncSession,
    *,
    student_id: int,
    resume_master_id: int,
    jobs: list[Job],
    profile: StudentProfile,
) -> dict[int, MatchBreakdown]:
    """Score a page of postings, reading from storage where available and computing the rest.

    Returns a breakdown keyed by job id, in the order the caller gave.
    """
    now = datetime.now(UTC)
    job_ids = [j.id for j in jobs]

    # Already stored?
    existing_stmt = select(MatchScore).where(
        MatchScore.student_id == student_id,
        MatchScore.resume_master_id == resume_master_id,
        MatchScore.job_id.in_(job_ids),
    )
    existing = {row.job_id: row for row in (await session.execute(existing_stmt)).scalars().all()}

    results: dict[int, MatchBreakdown] = {}
    to_insert: list[MatchScore] = []

    for job in jobs:
        if job.id in existing:
            row = existing[job.id]
            results[job.id] = _row_to_breakdown(row)
            continue

        posting_skills = set(job.extracted_skills or []) | extract_skills(job.description or "")
        requirement = parse_experience_requirement(job.title, job.description or "")

        breakdown = score_job(
            profile,
            posting_skills=posting_skills,
            requirement=requirement,
            description=job.description or "",
            posted_at=job.posted_at or job.first_seen_at,
            now=now,
        )
        results[job.id] = breakdown

        to_insert.append(
            MatchScore(
                student_id=student_id,
                job_id=job.id,
                resume_master_id=resume_master_id,
                total=breakdown.total,
                skill_points=breakdown.skill_points,
                experience_points=breakdown.experience_points,
                keyword_points=breakdown.keyword_points,
                freshness_points=breakdown.freshness_points,
                skill_state=breakdown.skill_state.value,
                experience_state=breakdown.experience_state.value,
                keyword_state=breakdown.keyword_state.value,
                freshness_state=breakdown.freshness_state.value,
                matched_skills=breakdown.matched_skills,
                missing_skills=breakdown.missing_skills,
                required_years=breakdown.required_years,
                requirement_basis=breakdown.requirement_basis.value if breakdown.requirement_basis else None,
                requirement_phrase=breakdown.requirement_phrase,
            )
        )

    if to_insert:
        session.add_all(to_insert)
        await session.flush()

    return results


def _row_to_breakdown(row: MatchScore) -> MatchBreakdown:
    from app.domain.experience import Basis
    from app.domain.scoring import ComponentState

    return MatchBreakdown(
        total=row.total,
        skill_points=row.skill_points,
        experience_points=row.experience_points,
        keyword_points=row.keyword_points,
        freshness_points=row.freshness_points,
        skill_state=ComponentState(row.skill_state),
        experience_state=ComponentState(row.experience_state),
        keyword_state=ComponentState(row.keyword_state),
        freshness_state=ComponentState(row.freshness_state),
        matched_skills=row.matched_skills or [],
        missing_skills=row.missing_skills or [],
        required_years=row.required_years,
        requirement_basis=Basis(row.requirement_basis) if row.requirement_basis else Basis.UNSTATED,
        requirement_phrase=row.requirement_phrase,
        is_complete=True,
    )


# How many filtered postings are scored before ranking. Bounded because ordering by score is in
# tension with computing scores lazily: you cannot sort by a number you have not calculated.
#
# 200 is chosen from the index rather than taste. The graduate software filter returns about 170
# postings, so in practice the whole relevant set is ranked and the ordering is genuinely global.
# Beyond the cap the feed falls back to recency for the tail, which is the honest failure mode —
# the alternative, scoring all 4,437 rows per student, is the cost ADR 0003 refused.
MAX_RANKED = 200


def rank_by_score(
    jobs: list[Job], scores: dict[int, MatchBreakdown]
) -> list[Job]:
    """Order postings by score, highest first, with a stable tiebreak.

    The tiebreak is the job id, not the score alone. Without it, two postings on the same total
    could swap between page 1 and page 2 of the same session, so a student would see one posting
    twice and never see another — the classic unstable-pagination bug, and invisible in testing
    because it needs two equal scores to appear.
    """
    return sorted(
        jobs,
        key=lambda j: (-(scores[j.id].total if j.id in scores else -1), j.id),
    )
