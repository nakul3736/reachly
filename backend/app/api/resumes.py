from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.resume_parser import get_resume_parser
from app.api.auth import CurrentUser
from app.db import get_session
from app.domain.parsed_resume import ParsedResume
from app.errors import NoActiveResume, ResumeNotFound, ResumeTooLarge
from app.schemas.resume import ResumeVersionSummary
from app.services import resume_service, student_service
from app.services.resume_service import MAX_RESUME_BYTES

router = APIRouter(prefix="/resumes", tags=["resumes"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_CHUNK_BYTES = 64 * 1024

# Multipart framing — boundary, headers, trailer — makes the request body slightly
# larger than the file itself. The header check is a fast pre-filter, so it allows for
# that; the chunked read below is what enforces the cap exactly.
_MULTIPART_ALLOWANCE = 8 * 1024


async def _read_within_cap(file: UploadFile, declared_length: int | None) -> bytes:
    """Read the upload, refusing to accumulate more than the cap.

    The Content-Length check rejects an oversized upload without reading it at all.
    It is not sufficient on its own — the header is client-supplied and can lie or be
    absent under chunked encoding — so the running total is the authoritative guard.
    """
    too_large_to_read = (
        declared_length is not None
        and declared_length > MAX_RESUME_BYTES + _MULTIPART_ALLOWANCE
    )
    if too_large_to_read:
        raise ResumeTooLarge

    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_RESUME_BYTES:
            raise ResumeTooLarge
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=ResumeVersionSummary, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    content_length: Annotated[int | None, Header()] = None,
) -> ResumeVersionSummary:
    """Store an upload as a new version, parsed.

    Validation and parsing both happen before anything is written, so a rejected or
    unparseable upload leaves the student's existing active resume exactly as it was and
    does not consume a version number. A gap in the numbering is a question the student
    cannot answer, and an active resume containing nothing is worse than no resume at
    all — tailoring would silently have no evidence to draw on.
    """
    student = await student_service.get_by_user_id(session, user.id)
    data = await _read_within_cap(file, content_length)
    resume_service.validate_pdf(data)
    parsed = await get_resume_parser().parse(data)
    resume = await resume_service.store_new_version(
        session, student.id, file.filename or "resume.pdf", data, parsed
    )
    return ResumeVersionSummary.model_validate(resume)


@router.get("/parsed", response_model=ParsedResume)
async def read_active_parsed_resume(user: CurrentUser, session: SessionDep) -> ParsedResume:
    """The structured form of the active resume.

    Declared before `/{resume_id}/parsed` so the literal path wins the match.
    """
    student = await student_service.get_by_user_id(session, user.id)
    active = await resume_service.get_active(session, student.id)
    if active is None:
        raise NoActiveResume
    return resume_service.parsed_of(active)


@router.get("/{resume_id}/parsed", response_model=ParsedResume)
async def read_parsed_resume(
    resume_id: int, user: CurrentUser, session: SessionDep
) -> ParsedResume:
    student = await student_service.get_by_user_id(session, user.id)
    resume = await resume_service.get_owned(session, student.id, resume_id)
    if resume is None:
        raise ResumeNotFound
    return resume_service.parsed_of(resume)


@router.get("", response_model=list[ResumeVersionSummary])
async def list_resumes(user: CurrentUser, session: SessionDep) -> list[ResumeVersionSummary]:
    student = await student_service.get_by_user_id(session, user.id)
    versions = await resume_service.list_for_student(session, student.id)
    return [ResumeVersionSummary.model_validate(version) for version in versions]


@router.get("/{resume_id}/file")
async def download_resume(resume_id: int, user: CurrentUser, session: SessionDep) -> Response:
    """The original bytes, unchanged.

    Another student's resume answers 404 rather than 403: a refusal that confirms the
    row exists still tells them something they should not learn.
    """
    student = await student_service.get_by_user_id(session, user.id)
    resume = await resume_service.get_owned(session, student.id, resume_id)
    if resume is None:
        raise ResumeNotFound

    return Response(
        content=resume.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{resume.filename}"'},
    )
