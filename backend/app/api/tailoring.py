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
from app.services.tailoring_service import RevisionRequest, revise_bullets, tailor_resume


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

    # True when no rewrite was attempted: no model available, the call failed, or the model omitted
    # this bullet from its answer. Defaults False so tailorings stored before this field existed load
    # as "considered", which is what they were.
    unavailable: bool = False


class DocumentBullet(BaseModel):
    """A bullet as it would appear on the page the student sends.

    `text` is their own sentence unless they approved a rewrite of it. That default is the feature:
    a proposal is not a change, and nothing reaches this document because a model suggested it.

    `pending` marks a rewrite that exists and has not been approved, so the preview can show the
    student what their resume would become without pretending it already has. `refused` marks a
    bullet where a rewrite was attempted and the validator rejected it — the attempt itself belongs
    on the comparison view, not here.
    """

    text: str
    applied: bool
    pending: bool
    refused: bool


class DocumentExperience(BaseModel):
    employer: str
    title: str
    dates: str
    bullets: list[DocumentBullet]


class DocumentProject(BaseModel):
    name: str
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
    projects: list[DocumentProject] = []
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

    # Which rewrites the student has approved. Empty means the document below is their own writing.
    approved_bullet_ids: list[str] = []

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
    """Put the approved rewrites back into the resume's own structure.

    Approved, not merely generated. A bullet the student has not ticked keeps their own sentence, so
    printing this before approving anything hands back their resume unchanged — the correct behaviour
    for a tool proposing edits to something an employer will read.

    Every bullet the resume has appears exactly once, in its original position. A bullet with no
    outcome — which happens when tailoring skipped it, or when a stored tailoring predates an
    edit — falls through to the student's own text rather than vanishing. Silently dropping a line
    from a document somebody is about to send an employer is the worst failure available here.
    """
    outcomes = {str(bullet.get("bullet_id")): bullet for bullet in (row.bullets or [])}
    approved = set(row.approved_bullet_ids or [])

    def render(bullet_id: str, own_text: str) -> DocumentBullet:
        """One bullet, resolved against what the student approved.

        Shared by experience and projects so the two sections cannot drift apart on the rule that
        matters most here: an unapproved rewrite is not applied.
        """
        outcome = outcomes.get(bullet_id)
        refused = bool(outcome and outcome.get("rejected_reason"))
        rewrite = str(outcome.get("tailored") or "") if outcome else ""
        offered = bool(outcome and outcome.get("changed")) and not refused
        applied = offered and bullet_id in approved

        return DocumentBullet(
            text=rewrite if applied and rewrite else own_text,
            applied=applied,
            pending=offered and not applied,
            refused=refused,
        )

    experience = [
        DocumentExperience(
            employer=entry.employer,
            title=entry.title,
            dates=entry.dates,
            bullets=[render(bullet.id, bullet.text) for bullet in entry.bullets],
        )
        for entry in parsed.experience
    ]

    projects = [
        DocumentProject(
            name=project.name,
            dates=project.dates,
            bullets=[render(bullet.id, bullet.text) for bullet in project.bullets],
        )
        for project in parsed.projects
    ]

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
        projects=projects,
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
        approved_bullet_ids=list(row.approved_bullet_ids or []),
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
            "unavailable": o.unavailable,
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
        # And it clears the approvals, which is the whole reason they are stored as ids beside the
        # payload rather than as a flag inside it. Every sentence here is newly generated; carrying a
        # tick across would mark text as approved that the student has never read, and the tick is
        # the one thing standing between a model's output and a document an employer receives.
        existing.approved_bullet_ids = []

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


class ApprovalRequest(BaseModel):
    """Which rewrites the student is willing to put their name to."""

    approved: list[str]


class BulletFeedback(BaseModel):
    bullet_id: str
    instruction: str


class ReviseRequest(BaseModel):
    """Feedback on several bullets at once, answered with one model call.

    `approved` is optional and carries the student's current ticks. It exists because feedback and
    approval happen on the same screen at the same time: a student ticks three suggestions, writes
    comments on two others, and presses send. Without it, the approvals still sitting in the browser
    were replaced by whatever the server last stored, and three ticks silently disappeared.
    """

    revisions: list[BulletFeedback]
    approved: list[str] | None = None


def _approvable(row: TailoredResume) -> set[str]:
    """Bullet ids whose rewrite the student could meaningfully approve.

    A refused rewrite is excluded: there is nothing to approve, because the text on offer is already
    the student's own, and a tick beside it would imply the guard had been overridden.
    """
    return {
        str(bullet.get("bullet_id"))
        for bullet in (row.bullets or [])
        if not bullet.get("rejected_reason")
    }


@router.post("/{job_id}/tailor/revise", response_model=TailoredResumeResponse)
async def revise(
    job_id: int,
    body: ReviseRequest,
    user: CurrentUser,
    session: SessionDep,
) -> TailoredResumeResponse:
    """Rewrite the bullets the student commented on, following their instructions, in one request.

    Batched deliberately. One call for the whole set, and at most two including the retry, so a
    student can iterate on six bullets for the same cost as one — which on a free tier is the
    difference between working freely and being rate-limited half way through a resume.

    An instruction can direct emphasis, length or ordering. It cannot authorise a fact: each result is
    validated against that bullet's own original exactly as the first pass was, so asking for a number
    the student's own sentence does not contain produces a refusal naming the number.

    Revising clears the approval for the bullets it touches. The student approved a particular
    sentence, and these are different ones.
    """
    feedback = [r for r in body.revisions if r.instruction.strip()]
    if not feedback:
        raise DomainError("Say what you would like changed, on at least one bullet.")

    job = await job_service.get_job(session, job_id)
    student = await _student_of(session, user.id)
    resume = await _active_resume(session, student.id)
    row = await _stored_tailoring(
        session, student_id=student.id, job_id=job.id, resume_id=resume.id
    )

    bullets = list(row.bullets or [])
    positions = {str(b.get("bullet_id")): i for i, b in enumerate(bullets)}

    unknown = [r.bullet_id for r in feedback if r.bullet_id not in positions]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Not part of this tailoring: {', '.join(unknown)}",
        )

    requests = [
        RevisionRequest(
            bullet_id=r.bullet_id,
            # Always the student's own sentence, never the last rewrite. See revise_bullets for why
            # chaining revisions against each other would let a claim arrive by degrees.
            original=str(bullets[positions[r.bullet_id]].get("original") or ""),
            instruction=r.instruction,
        )
        for r in feedback
    ]

    try:
        llm = get_llm_client()
    except LLMError:
        llm = None

    outcomes = await revise_bullets(
        requests,
        job_title=job.title,
        company=job.company_name,
        description=job.description or "",
        llm=llm,
    )

    # The ticks the student has on screen right now, if the client sent them, otherwise what was
    # last stored. Taking them from the request is what stops an unsaved approval being lost the
    # moment feedback is sent from the same screen.
    if body.approved is not None:
        approved = set(body.approved) & _approvable(row)
    else:
        approved = set(row.approved_bullet_ids or [])

    for outcome in outcomes:
        bullets[positions[outcome.bullet_id]] = {
            "bullet_id": outcome.bullet_id,
            "original": outcome.original,
            "tailored": outcome.tailored,
            "changed": outcome.changed,
            "rejected_reason": (
                outcome.rejected_reason.value if outcome.rejected_reason else None
            ),
            "rejected_detail": outcome.rejected_detail,
            "rejected_text": outcome.rejected_text,
            "unavailable": outcome.unavailable,
        }
        approved.discard(outcome.bullet_id)

    row.bullets = bullets
    row.changed_count = sum(1 for b in bullets if b.get("changed"))
    row.rejected_count = sum(1 for b in bullets if b.get("rejected_reason"))
    row.approved_bullet_ids = sorted(approved)

    await session.commit()
    await session.refresh(row)

    parsed = ParsedResume.model_validate(resume.parsed_json)
    return _to_response(job, row, parsed=parsed, student=student, email=user.email)


async def _stored_tailoring(
    session: AsyncSession, *, student_id: int, job_id: int, resume_id: int
) -> TailoredResume:
    row = (
        (
            await session.execute(
                select(TailoredResume).where(
                    TailoredResume.student_id == student_id,
                    TailoredResume.job_id == job_id,
                    TailoredResume.resume_master_id == resume_id,
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
    return row


@router.patch("/{job_id}/tailor/approvals", response_model=TailoredResumeResponse)
async def set_approvals(
    job_id: int,
    body: ApprovalRequest,
    user: CurrentUser,
    session: SessionDep,
) -> TailoredResumeResponse:
    """Record which rewrites the student accepts. Only these reach the document.

    The whole set is replaced rather than toggled one at a time, so the request describes the
    student's current intent completely and two screens cannot disagree about what was approved.

    Ids that do not belong to this tailoring are dropped rather than rejected with an error. The
    honest reading of an unknown id is that the resume moved on — a re-upload, a re-tailoring — and
    failing the request would leave a student unable to approve the seven bullets that are still
    valid because an eighth is stale.
    """
    job = await job_service.get_job(session, job_id)
    student = await _student_of(session, user.id)
    resume = await _active_resume(session, student.id)
    row = await _stored_tailoring(
        session, student_id=student.id, job_id=job.id, resume_id=resume.id
    )

    known = _approvable(row)
    row.approved_bullet_ids = sorted(set(body.approved) & known)

    await session.commit()
    await session.refresh(row)

    parsed = ParsedResume.model_validate(resume.parsed_json)
    return _to_response(job, row, parsed=parsed, student=student, email=user.email)
