from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentUser
from app.db import get_session
from app.models.student import Student
from app.schemas.student import StudentProfile, StudentProfileUpdate
from app.services import student_service

router = APIRouter(prefix="/students", tags=["students"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _as_profile(student: Student) -> StudentProfile:
    return StudentProfile(
        name=student.name,
        target_role=student.target_role,
        years_experience=student.years_experience,
        locations=list(student.locations),
        skills=list(student.skills),
        links=dict(student.links),
        missing_for_results=student_service.missing_for_results(student),
    )


@router.get("/me", response_model=StudentProfile)
async def read_my_profile(user: CurrentUser, session: SessionDep) -> StudentProfile:
    """The authenticated student's profile.

    No id in the path. A route shaped `/students/{id}` invites an ownership check
    that can be forgotten; with no id there is nothing to forget.
    """
    student = await student_service.get_by_user_id(session, user.id)
    return _as_profile(student)


@router.patch("/me", response_model=StudentProfile)
async def update_my_profile(
    changes: StudentProfileUpdate, user: CurrentUser, session: SessionDep
) -> StudentProfile:
    """Update the authenticated student's profile.

    Same shape as the read: the token selects the row, so there is no id to tamper
    with and no ownership check to omit.
    """
    student = await student_service.get_by_user_id(session, user.id)
    updated = await student_service.update(session, student, changes)
    return _as_profile(updated)
