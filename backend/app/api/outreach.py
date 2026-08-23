"""Outreach: a draft the student sends themselves.

ADR 0004 in one line — Reachly does not send email. This endpoint returns a finished message and the
evidence behind every claim in it; the handover is a `mailto:` link or the clipboard, and the sender
is the student, from their own address, having read what goes out under their name.

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

from app.api.auth import CurrentUser
from app.db import get_session
from app.domain.outreach import build_outreach_draft
from app.errors import DomainError
from app.models.job import Job
from app.models.student import Student
from app.services import job_service
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


@router.get("/{job_id}/outreach", response_model=OutreachResponse)
async def get_outreach(
    job_id: int,
    user: CurrentUser,
    session: SessionDep,
) -> OutreachResponse:
    """A draft introduction for this posting, assembled from facts rather than generated.

    No model call. Not to save quota — because generation is the wrong tool for this. A cold email is
    where a writing tool is most tempted to invent enthusiasm, and "I have long admired your work in
    distributed systems", sent to a company the student met ninety seconds ago, is worse for them than
    four plain sentences that are true. Assembling the draft deterministically makes it reproducible,
    instant, free, and incapable of flattering anybody with something Reachly cannot show.
    """
    job = await job_service.get_job(session, job_id)

    student = (
        (await session.execute(select(Student).where(Student.user_id == user.id)))
        .scalars()
        .first()
    )
    if student is None:
        raise ProfileMissing("Add your profile before drafting an introduction.")

    # The skills named in the message are the ones feature 03 already found in the resume. Recomputing
    # them here would risk the email claiming a skill the score does not credit.
    matched: list[str] = []
    profile = await get_student_profile(session, student.id)
    if profile is not None:
        from app.models.resume import ResumeMaster

        resume_id = (
            (
                await session.execute(
                    select(ResumeMaster.id).where(
                        ResumeMaster.student_id == student.id,
                        ResumeMaster.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .first()
        )
        if resume_id is not None:
            scores = await score_page(
                session,
                student_id=student.id,
                resume_master_id=resume_id,
                jobs=[job],
                profile=profile,
            )
            breakdown = scores.get(job.id)
            if breakdown is not None:
                matched = list(breakdown.matched_skills)

    other_roles = await _count_other_open_roles(session, job)

    draft = build_outreach_draft(
        student_name=student.name or "",
        job_title=job.title,
        company=job.company_name,
        matched_skills=matched,
        other_open_roles=other_roles,
    )

    return OutreachResponse(
        job_id=job.id,
        company_name=job.company_name,
        subject=draft.subject,
        body=draft.body,
        evidence=draft.evidence,
        apply_url=job.apply_url,
        other_open_roles=other_roles,
    )
