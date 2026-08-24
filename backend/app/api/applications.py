"""Application tracking: the pipeline, in the student's own words.

Every status here is reported by the student, never inferred. Reachly does not submit the form and does
not send the email (ADR 0004), so it has no view of what happened — and a tracker that guessed would be
wrong in the direction that hurts, marking a posting applied because a link was clicked when the student
read the form and closed it. Clicking apply opens a tab; saying you applied is a separate, deliberate act.

What makes this more than a bookmark list is the pointer to the tailored resume that was actually sent.
Two months later an interview invitation arrives and the question is "what did I claim?", which cannot be
answered from a job title and a date.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentUser
from app.db import get_session
from app.errors import DomainError
from app.models.application import Application, ApplicationStatus
from app.models.job import Job
from app.models.student import Student
from app.models.tailored_resume import TailoredResume
from app.services import job_service

router = APIRouter(prefix="/applications", tags=["applications"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class ProfileMissing(DomainError):
    status_code = 409
    code = "profile_missing"


class ApplicationNotFound(DomainError):
    status_code = 404
    code = "application_not_found"


class ApplicationView(BaseModel):
    id: int
    job_id: int
    title: str
    company_name: str
    apply_url: str
    status: ApplicationStatus
    notes: str

    # Present when the student sent a tailored version, so the row can link to exactly what went out.
    tailored_resume_id: int | None
    has_tailored_resume: bool

    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # True when the posting has since been taken down. Shown rather than hidden: a closed posting with
    # an outstanding application is information, and quietly dropping the row would read as data loss.
    closed: bool


class PipelineResponse(BaseModel):
    items: list[ApplicationView]

    # One count per status, including zeros, so the interface can render a stable set of columns
    # instead of columns that appear and vanish as the pipeline changes shape.
    counts: dict[ApplicationStatus, int]


class TrackRequest(BaseModel):
    job_id: int
    status: ApplicationStatus = ApplicationStatus.SAVED
    notes: str = ""


class UpdateRequest(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)


async def _student_of(session: AsyncSession, user_id: int) -> Student:
    student = (
        (await session.execute(select(Student).where(Student.user_id == user_id))).scalars().first()
    )
    if student is None:
        raise ProfileMissing("Add your profile before tracking applications.")
    return student


async def _tailored_resume_id(session: AsyncSession, *, student_id: int, job_id: int) -> int | None:
    """The most recent tailoring for this posting, if there is one.

    Attached at the moment the student reports applying rather than looked up on read. The lookup
    version answers "what is the newest tailoring?" when the question is "what did I send?" — and those
    diverge the moment they tailor again for a second, similar posting.
    """
    return (
        (
            await session.execute(
                select(TailoredResume.id)
                .where(
                    TailoredResume.student_id == student_id,
                    TailoredResume.job_id == job_id,
                )
                .order_by(TailoredResume.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


def _view(application: Application, job: Job) -> ApplicationView:
    return ApplicationView(
        id=application.id,
        job_id=job.id,
        title=job.title,
        company_name=job.company_name,
        apply_url=job.apply_url,
        status=ApplicationStatus(application.status),
        notes=application.notes or "",
        tailored_resume_id=application.tailored_resume_id,
        has_tailored_resume=application.tailored_resume_id is not None,
        applied_at=application.applied_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
        closed=job.closed_at is not None,
    )


@router.get("", response_model=PipelineResponse)
async def list_applications(user: CurrentUser, session: SessionDep) -> PipelineResponse:
    """Everything the student is pursuing, newest activity first."""
    student = await _student_of(session, user.id)

    rows = (
        (
            await session.execute(
                select(Application, Job)
                .join(Job, Job.id == Application.job_id)
                .where(Application.student_id == student.id)
                .order_by(Application.updated_at.desc())
            )
        )
        .tuples()
        .all()
    )

    counts = dict.fromkeys(ApplicationStatus, 0)
    for application, _job in rows:
        counts[ApplicationStatus(application.status)] += 1

    return PipelineResponse(
        items=[_view(application, job) for application, job in rows], counts=counts
    )


@router.get("/for-job/{job_id}", response_model=ApplicationView | None)
async def for_job(job_id: int, user: CurrentUser, session: SessionDep) -> ApplicationView | None:
    """This student's application for one posting, or null when it is not tracked.

    Declared before `/{application_id}` so the literal segment wins the match — the same ordering trap
    the resume endpoints hit, where `/parsed` was being read as an id.

    Null rather than 404 for an untracked posting. "Not tracked" is a normal state that the posting page
    asks about on every visit, and a 404 would make the ordinary case look like an error in the console
    and in any error reporting.
    """
    student = await _student_of(session, user.id)

    row = (
        (
            await session.execute(
                select(Application, Job)
                .join(Job, Job.id == Application.job_id)
                .where(Application.student_id == student.id, Application.job_id == job_id)
            )
        )
        .tuples()
        .first()
    )
    if row is None:
        return None

    application, job = row
    return _view(application, job)


@router.post("", response_model=ApplicationView, status_code=201)
async def track(body: TrackRequest, user: CurrentUser, session: SessionDep) -> ApplicationView:
    """Start tracking a posting, or update the one already tracked.

    Idempotent on (student, posting) rather than failing on a duplicate. The student pressing "I
    applied" twice means they applied; an error would be pedantry about a fact they are asserting.
    """
    student = await _student_of(session, user.id)
    job = await job_service.get_job(session, body.job_id)

    application = (
        (
            await session.execute(
                select(Application).where(
                    Application.student_id == student.id, Application.job_id == job.id
                )
            )
        )
        .scalars()
        .first()
    )

    if application is None:
        application = Application(student_id=student.id, job_id=job.id)
        session.add(application)

    application.status = body.status
    if body.notes:
        application.notes = body.notes

    if body.status == ApplicationStatus.APPLIED and application.applied_at is None:
        application.applied_at = datetime.now(UTC)
        application.tailored_resume_id = await _tailored_resume_id(
            session, student_id=student.id, job_id=job.id
        )

    await session.commit()
    await session.refresh(application)
    return _view(application, job)


@router.patch("/{application_id}", response_model=ApplicationView)
async def update(
    application_id: int, body: UpdateRequest, user: CurrentUser, session: SessionDep
) -> ApplicationView:
    """Move a posting along the pipeline, or write a note against it."""
    student = await _student_of(session, user.id)

    application = (
        (
            await session.execute(
                select(Application).where(
                    Application.id == application_id, Application.student_id == student.id
                )
            )
        )
        .scalars()
        .first()
    )
    if application is None:
        # 404 rather than 403 for a row belonging to somebody else: a different code would confirm the
        # id exists, which is the one thing an enumeration attempt is trying to learn.
        raise ApplicationNotFound("No such application.")

    if body.status is not None:
        application.status = body.status
        if body.status == ApplicationStatus.APPLIED and application.applied_at is None:
            application.applied_at = datetime.now(UTC)
            application.tailored_resume_id = await _tailored_resume_id(
                session, student_id=student.id, job_id=application.job_id
            )

    if body.notes is not None:
        application.notes = body.notes

    await session.commit()
    await session.refresh(application)

    job = await job_service.get_job(session, application.job_id)
    return _view(application, job)


@router.delete("/{application_id}", status_code=204)
async def untrack(application_id: int, user: CurrentUser, session: SessionDep) -> None:
    """Stop tracking entirely.

    Distinct from `withdrawn`, which keeps the history. This is for the posting saved by mistake.
    """
    student = await _student_of(session, user.id)

    application = (
        (
            await session.execute(
                select(Application).where(
                    Application.id == application_id, Application.student_id == student.id
                )
            )
        )
        .scalars()
        .first()
    )
    if application is None:
        raise ApplicationNotFound("No such application.")

    await session.delete(application)
    await session.commit()
