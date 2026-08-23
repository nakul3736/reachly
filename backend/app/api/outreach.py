"""Outreach: a draft the student sends themselves.

ADR 0004 in one line — Reachly does not send email. This endpoint returns a finished message and the
evidence behind every claim in it; the handover is a `mailto:` link or the clipboard, and the sender
is the student, from their own address, having read what goes out under their name.

The message is written by a model from the student's own resume and the actual posting, and then
checked against the resume before they ever see it (`app/services/outreach_service.py`). When the check
refuses it twice, or no model is available, the assembled draft from `app/domain/outreach.py` is
returned instead and the response says so — a template presented as writing is a small lie the student
discovers by reading it.

Drafts are stored per posting per resume upload. A page visit must not spend a model call, and a
student needs to re-read what they sent; re-uploading a resume produces a fresh draft rather than an
email describing work they have since removed.

There is no contact discovery here. ADR 0004 specified a waterfall of Hunter, Prospeo and Tomba with
MailboxLayer verification, and that remains the right design when the keys exist — but guessing an
address and presenting it hopefully is worse than asking, because a bounce costs the student the
opportunity and they will never know it happened. So the recipient is supplied by the student, from
the company's own site, and the apply link remains the path that cannot fail.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.llm_client import get_llm_client
from app.api.auth import CurrentUser
from app.db import get_session
from app.errors import DomainError
from app.models.job import Job
from app.models.outreach_draft import OutreachDraftRow
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.services import job_service, resume_service
from app.services.outreach_service import write_outreach
from app.services.scoring_service import get_student_profile, score_page

router = APIRouter(prefix="/jobs", tags=["outreach"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class ProfileMissing(DomainError):
    status_code = 409
    code = "profile_missing"


class OutreachResponse(BaseModel):
    job_id: int
    company_name: str
    subject: str
    body: str

    # Why the message says what it says. The same argument the score report makes for the score: a
    # claim a student cannot check is a claim they have to take on trust, and this one goes out under
    # their name.
    evidence: list[str]

    # True when a model wrote it from the resume and posting and the result passed the fabrication
    # check; False when this is the assembled fallback.
    written: bool

    # Present so the interface can be honest that Reachly is not finding the address. ADR 0004.
    apply_url: str
    other_open_roles: int


async def _count_other_open_roles(session: AsyncSession, job: Job) -> int:
    """How many other live postings this company has.

    The personalisation hook ADR 0001 settled on after LinkedIn was ruled out. It is worth more than
    it looks: because the index ingests whole boards rather than individual postings, this is a real
    observation about a company's trajectory, and it costs one count.
    """
    stmt = (
        select(func.count())
        .select_from(Job)
        .where(
            Job.company_name == job.company_name,
            Job.id != job.id,
            Job.closed_at.is_(None),
        )
    )
    return int((await session.execute(stmt)).scalar() or 0)


async def _student_of(session: AsyncSession, user_id: int) -> Student:
    student = (
        (await session.execute(select(Student).where(Student.user_id == user_id)))
        .scalars()
        .first()
    )
    if student is None:
        raise ProfileMissing("Add your profile before drafting an introduction.")
    return student


async def _active_resume(session: AsyncSession, student_id: int) -> ResumeMaster | None:
    return (
        (
            await session.execute(
                select(ResumeMaster).where(
                    ResumeMaster.student_id == student_id,
                    ResumeMaster.is_active.is_(True),
                )
            )
        )
        .scalars()
        .first()
    )


async def _matched_skills(
    session: AsyncSession, *, student: Student, resume: ResumeMaster | None, job: Job
) -> list[str]:
    """The overlap feature 03 already computed, never recomputed here.

    One source means the email cannot name a skill the score does not credit, and the student cannot
    find the two screens disagreeing about what their resume evidences.
    """
    if resume is None:
        return []
    profile = await get_student_profile(session, student.id)
    if profile is None:
        return []

    scores = await score_page(
        session,
        student_id=student.id,
        resume_master_id=resume.id,
        jobs=[job],
        profile=profile,
    )
    breakdown = scores.get(job.id)
    return list(breakdown.matched_skills) if breakdown is not None else []


async def _build(
    session: AsyncSession, *, job_id: int, user_id: int, force: bool
) -> OutreachResponse:
    job = await job_service.get_job(session, job_id)
    student = await _student_of(session, user_id)
    resume = await _active_resume(session, student.id)
    other_roles = await _count_other_open_roles(session, job)

    stored = (
        (
            await session.execute(
                select(OutreachDraftRow).where(
                    OutreachDraftRow.student_id == student.id,
                    OutreachDraftRow.job_id == job.id,
                    OutreachDraftRow.resume_master_id == (resume.id if resume else None),
                )
            )
        )
        .scalars()
        .first()
    )

    if stored is not None and not force:
        return OutreachResponse(
            job_id=job.id,
            company_name=job.company_name,
            subject=stored.subject,
            body=stored.body,
            evidence=list(stored.evidence or []),
            written=stored.written,
            apply_url=job.apply_url,
            other_open_roles=other_roles,
        )

    matched = await _matched_skills(session, student=student, resume=resume, job=job)
    parsed = resume_service.parsed_of(resume) if resume is not None else None

    draft = await write_outreach(
        student_name=student.name or "",
        job_title=job.title,
        company=job.company_name,
        description=job.description or "",
        resume=parsed,
        matched_skills=matched,
        other_open_roles=other_roles,
        llm=get_llm_client(),
    )

    if stored is None:
        stored = OutreachDraftRow(
            student_id=student.id,
            job_id=job.id,
            resume_master_id=resume.id if resume else None,
        )
        session.add(stored)

    stored.subject = draft.subject
    stored.body = draft.body
    stored.evidence = list(draft.evidence)
    stored.written = draft.written

    # Explicit, because `get_session` does not commit. Three write paths were silently discarding
    # their work for exactly this reason before it was found.
    await session.commit()

    return OutreachResponse(
        job_id=job.id,
        company_name=job.company_name,
        subject=draft.subject,
        body=draft.body,
        evidence=draft.evidence,
        written=draft.written,
        apply_url=job.apply_url,
        other_open_roles=other_roles,
    )


@router.get("/{job_id}/outreach", response_model=OutreachResponse)
async def get_outreach(job_id: int, user: CurrentUser, session: SessionDep) -> OutreachResponse:
    """The stored draft for this posting, written on first request."""
    return await _build(session, job_id=job_id, user_id=user.id, force=False)


@router.post("/{job_id}/outreach/rewrite", response_model=OutreachResponse)
async def rewrite_outreach(
    job_id: int, user: CurrentUser, session: SessionDep
) -> OutreachResponse:
    """Write it again.

    Generation is not deterministic, so a second attempt is a genuinely different email rather than a
    retry of the same one — which is the honest answer to "I don't like this draft" when the student has
    no way to instruct a rewrite. It is a POST because it spends a model call and replaces the stored
    draft; a GET that did that would be re-run by every prefetch and refresh.
    """
    return await _build(session, job_id=job_id, user_id=user.id, force=True)
