"""Storing and listing resume versions.

No FastAPI imports — see `.kiro/steering/backend.md`.
"""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ResumeTooLarge, UnsupportedResumeFormat
from app.models.resume import ResumeMaster

# Generous for a resume, small enough that a whole row still fits comfortably in a
# 1GB database and that a malicious upload cannot exhaust memory.
MAX_RESUME_BYTES = 5 * 1024 * 1024

# Every PDF begins with this. Checked instead of the extension or the declared
# content type, both of which the client chooses and neither of which is evidence.
PDF_MAGIC = b"%PDF-"


def validate_pdf(data: bytes) -> None:
    """Reject anything that is not a PDF, by its bytes.

    Order matters: size is checked first because it is the cheaper rejection, and
    because a caller who sent 40MB should be told that rather than being told their
    file is the wrong type.
    """
    if len(data) > MAX_RESUME_BYTES:
        raise ResumeTooLarge
    if not data.startswith(PDF_MAGIC):
        raise UnsupportedResumeFormat


async def store_new_version(
    session: AsyncSession, student_id: int, filename: str, data: bytes
) -> ResumeMaster:
    """Store an upload as the next version and make it the active one.

    Deactivating the previous version and activating the new one happen in a single
    transaction. A failure between the two would otherwise leave the student with no
    active resume — and nothing in the interface would explain why tailoring had
    stopped working.

    The uniqueness of `(student_id, version)` and of the active row are both enforced
    by the database, so this ordering is a correctness measure rather than the only
    thing preventing two active resumes.
    """
    highest = await session.scalar(
        select(func.max(ResumeMaster.version)).where(ResumeMaster.student_id == student_id)
    )

    await session.execute(
        update(ResumeMaster)
        .where(ResumeMaster.student_id == student_id, ResumeMaster.is_active)
        .values(is_active=False)
    )

    resume = ResumeMaster(
        student_id=student_id,
        version=(highest or 0) + 1,
        filename=filename,
        byte_size=len(data),
        pdf_bytes=data,
        is_active=True,
    )
    session.add(resume)
    await session.commit()
    await session.refresh(resume)
    return resume


async def list_for_student(session: AsyncSession, student_id: int) -> list[ResumeMaster]:
    """Newest first — the version a student is looking for is almost always the last."""
    result = await session.execute(
        select(ResumeMaster)
        .where(ResumeMaster.student_id == student_id)
        .order_by(ResumeMaster.version.desc())
    )
    return list(result.scalars())


async def get_owned(
    session: AsyncSession, student_id: int, resume_id: int
) -> ResumeMaster | None:
    """Fetch by id, scoped to the owner.

    Ownership is part of the query rather than a check after it. A separate check is
    something that can be forgotten at one call site; a scoped query cannot return a
    row that fails it.
    """
    result = await session.execute(
        select(ResumeMaster).where(
            ResumeMaster.id == resume_id, ResumeMaster.student_id == student_id
        )
    )
    return result.scalar_one_or_none()
