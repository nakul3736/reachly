"""Reading and updating the student profile.

No FastAPI imports — see `.kiro/steering/backend.md`.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student
from app.schemas.student import REQUIRED_FOR_RESULTS, StudentProfileUpdate


def missing_for_results(student: Student) -> list[str]:
    """Which fields still need a value before the feed can produce anything.

    A pure function of the row so it can be asserted directly, and so the same rule
    is used by the feed when it decides whether to explain an empty result.
    """
    return [
        field for field in REQUIRED_FOR_RESULTS if not getattr(student, field, None)
    ]


async def get_by_user_id(session: AsyncSession, user_id: int) -> Student:
    """The profile belonging to a user.

    Raises rather than returning None: a student row is created during registration,
    so its absence is a broken invariant and not a case for the caller to handle.
    """
    result = await session.execute(select(Student).where(Student.user_id == user_id))
    return result.scalar_one()


async def update(
    session: AsyncSession, student: Student, changes: StudentProfileUpdate
) -> Student:
    """Apply only the fields present in the request.

    `exclude_unset` is doing the load-bearing work. Without it, a field absent from
    the body would arrive as None and overwrite a real value — the bug where editing
    one field wipes the rest.

    An explicit null is still a change, because clearing a field the student had
    filled in is a legitimate thing to want.
    """
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(student, field, value)
    await session.commit()
    await session.refresh(student)
    return student
