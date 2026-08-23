"""Tailoring a resume to a posting.

A POST because it creates something and costs a model call, and because a GET that spent quota
would be fetched by every crawler and link preview that touched the URL.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.llm_client import LLMError, get_llm_client
from app.api.auth import CurrentUser
from app.config import get_settings
from app.db import get_session
from app.domain.parsed_resume import ParsedResume
from app.errors import DomainError
from app.models.job import Job
from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.tailored_resume import TailoredResume
from app.services import job_service
from app.services.scoring_service import get_student_profile, score_page
from app.services.tailoring_service import tailor_resume


class ProfileMissing(DomainError):
    status_code = 409
    code = "profile_missing"


class ResumeMissing(DomainError):
    status_code = 409
    code = "resume_missing"


router = APIRouter(prefix="/jobs", tags=["tailoring"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class TailoredBullet(BaseModel):
    bullet_id: str
    original: str
    tailored: str
    changed: bool

    # Present only when a rewrite was refused. The interface shows the student what was caught
    # rather than asking them to trust that something was.
    rejected_reason: str | None = None
    rejected_detail: str = ""
    rejected_text: str = ""


class DocumentBullet(BaseModel):
    """A bullet as it should appear on the page.

    `text` is what the student would send: the rewrite where one was accepted, and their own
    original wherever it was not. `refused` marks the second case, so the preview can be honest
    about which lines a model tried and failed to improve without cluttering the page with the
    attempt itself — that belongs on the comparison view.
    """

    text: str
    changed: bool
    refused: bool


class DocumentExperience(BaseModel):
    employer: str
    title: str
    dates: str
    bullets: list[DocumentBullet]


class DocumentEducation(BaseModel):
    institution: str
    credential: str
    dates: str


class TailoredDocument(BaseModel):
    """The whole resume, assembled with the accepted rewrites in place.

    Assembled on the server rather than joined in the browser. The alternative — returning bullets
    and letting the client stitch them back into the resume it fetched separately — means two
    payloads that can disagree about which bullet belongs to which job, and the failure mode is a
    student sending an employer a bullet filed under the wrong role.

    Order is the resume's own order throughout. Tailoring rewrites sentences; it does not decide
    that one of the student's jobs matters more than another.
    """

    name: str
    email: str
    links: dict[str, str]
    summary: str
    skills: list[str]
    experience: list[DocumentExperience]
    education: list[DocumentEducation]


class TailoredResumeResponse(BaseModel):
    job_id: int
    job_title: str
    company_name: str

    bullets: list[TailoredBullet]
    gaps: list[str]

    changed_count: int
    rejected_count: int

    # recorded | live. A tailoring from a fixture is a weaker claim than one from a model, and
    # the product's position is that it never presents one as the other.
    basis: str

    created_at: datetime

    # The printable version. Present so the student can see the result as a document rather than
    # as a list of sentences, and take it away without retyping it.
    document: TailoredDocument


async def _student_of(session: AsyncSession, user_id: int) -> Student:
    student = (
        (await session.execute(select(Student).where(Student.user_id == user_id)))
        .scalars()
        .first()
    )
    if student is None:
        raise ProfileMissing("Add your profile before tailoring a resume.")
    return student


async def _active_resume(session: AsyncSession, student_id: int) -> ResumeMaster:
    resume = (
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

    if resume is None or resume.parsed_json is None:
        raise ResumeMissing(
            "Upload a resume first. Tailoring rewrites your own bullets, so there has to be "
            "something to rewrite."
        )
    return resume


def _assemble_document(
    parsed: ParsedResume,
    row: TailoredResume,
    *,
    student: Student,
    email: str,
) -> TailoredDocument:
    """Put the accepted rewrites back into the resume's own structure.

    Every bullet the resume has appears exactly once, in its original position. A bullet with no
    outcome — which happens when tailoring skipped it, or when a stored tailoring predates an
    edit — falls through to the student's own text rather than vanishing. Silently dropping a line
    from a document somebody is about to send an employer is the worst failure available here.
    """
    outcomes = {str(bullet.get("bullet_id")): bullet for bullet in (row.bullets or [])}

    experience: list[DocumentExperience] = []
    for entry in parsed.experience:
        bullets: list[DocumentBullet] = []
        for bullet in entry.bullets:
            outcome = outcomes.get(bullet.id)
            refused = bool(outcome and outcome.get("rejected_reason"))
            tailored = str(outcome.get("tailored") or "") if outcome else ""
            bullets.append(
                DocumentBullet(
                    text=tailored or bullet.text,
                    changed=bool(outcome and outcome.get("changed")),
                    refused=refused,
                )
            )
        experience.append(
            DocumentExperience(
                employer=entry.employer,
                title=entry.title,
                dates=entry.dates,
                bullets=bullets,
            )
        )

    return TailoredDocument(
        name=student.name or "",
        email=email,
        links=dict(student.links or {}),
        summary=parsed.summary,
        # The resume's own skills, untouched. The posting's missing skills are gaps and are shown
        # as gaps; writing them into a skills list would be the fabrication this feature exists to
        # prevent, and it is the easiest place to do it by accident.
        skills=list(parsed.skills),
        experience=experience,
        education=[
            DocumentEducation(
                institution=entry.institution,
                credential=entry.credential,
                dates=entry.dates,
            )
            for entry in parsed.education
        ],
    )


def _to_response(
    job: Job,
    row: TailoredResume,
    *,
    parsed: ParsedResume,
    student: Student,
    email: str,
) -> TailoredResumeResponse:
    return TailoredResumeResponse(
        job_id=job.id,
        job_title=job.title,
        company_name=job.company_name,
        bullets=[TailoredBullet.model_validate(b) for b in row.bullets],
        gaps=list(row.gaps or []),
        changed_count=row.changed_count,
        rejected_count=row.rejected_count,
        basis=row.basis,
        created_at=row.created_at,
        document=_assemble_document(parsed, row, student=student, email=email),
    )


@router.post("/{job_id}/tailor", response_model=TailoredResumeResponse)
async def create_tailoring(
    job_id: int,
    user: CurrentUser,
    session: SessionDep,
) -> TailoredResumeResponse:
    """Rewrite the student's bullets for this posting, keeping anything unverifiable unchanged."""
    job = await job_service.get_job(session, job_id)
    student = await _student_of(session, user.id)
    resume = await _active_resume(session, student.id)

    parsed = ParsedResume.model_validate(resume.parsed_json)

    # The gap list is not computed here. It is feature 03's `missing_skills`, already derived for
    # this job and this student, so tailoring and the score can never disagree about what the
    # posting wanted and the resume lacks.
    gaps: list[str] = []
    profile = await get_student_profile(session, student.id)
    if profile is not None:
        scores = await score_page(
            session,
            student_id=student.id,
            resume_master_id=resume.id,
            jobs=[job],
            profile=profile,
        )
        breakdown = scores.get(job.id)
        if breakdown is not None:
            gaps = list(breakdown.missing_skills)

    settings = get_settings()
    try:
        llm = get_llm_client()
    except LLMError:
        llm = None

    result = await tailor_resume(
        parsed,
        job_title=job.title,
        company=job.company_name,
        description=job.description or "",
        missing_skills=gaps,
        llm=llm,
    )

    payload: list[dict[str, object]] = [
        {
            "bullet_id": o.bullet_id,
            "original": o.original,
            "tailored": o.tailored,
            "changed": o.changed,
            "rejected_reason": o.rejected_reason.value if o.rejected_reason else None,
            "rejected_detail": o.rejected_detail,
            "rejected_text": o.rejected_text,
        }
        for o in result.outcomes
    ]

    existing = (
        (
            await session.execute(
                select(TailoredResume).where(
                    TailoredResume.student_id == student.id,
                    TailoredResume.job_id == job.id,
                    TailoredResume.resume_master_id == resume.id,
                )
            )
        )
        .scalars()
        .first()
    )

    basis = "recorded" if settings.demo_mode else "live"

    if existing is None:
        existing = TailoredResume(
            student_id=student.id,
            job_id=job.id,
            resume_master_id=resume.id,
            bullets=payload,
            gaps=result.gaps,
            changed_count=result.changed_count,
            rejected_count=result.rejected_count,
            basis=basis,
        )
        session.add(existing)
    else:
        # Re-tailoring replaces rather than accumulating rows nobody would choose between.
        existing.bullets = payload
        existing.gaps = result.gaps
        existing.changed_count = result.changed_count
        existing.rejected_count = result.rejected_count
        existing.basis = basis

    # Committed rather than flushed. `get_session` never commits, so a flush alone meant the
    # tailoring existed for the length of the response and then vanished: a student who tailored a
    # resume, navigated away and came back was told there was no tailoring for this posting, and
    # every visit spent another model call redoing work that had already been done and approved.
    await session.commit()
    await session.refresh(existing)
    return _to_response(job, existing, parsed=parsed, student=student, email=user.email)


@router.get("/{job_id}/tailor", response_model=TailoredResumeResponse)
async def get_tailoring(
    job_id: int,
    user: CurrentUser,
    session: SessionDep,
) -> TailoredResumeResponse:
    """The stored tailoring for this posting, so a student can review what they sent."""
    job = await job_service.get_job(session, job_id)
    student = await _student_of(session, user.id)
    resume = await _active_resume(session, student.id)

    row = (
        (
            await session.execute(
                select(TailoredResume).where(
                    TailoredResume.student_id == student.id,
                    TailoredResume.job_id == job.id,
                    TailoredResume.resume_master_id == resume.id,
                )
            )
        )
        .scalars()
        .first()
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tailoring for this posting yet.",
        )

    parsed = ParsedResume.model_validate(resume.parsed_json)
    return _to_response(job, row, parsed=parsed, student=student, email=user.email)
