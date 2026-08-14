"""What the upload endpoint refuses.

The property that matters most is at the bottom: a rejected upload must leave the
student's existing active resume exactly as it was. A failed upload that silently
deactivates the working resume would break tailoring with no visible cause.
"""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import ResumeMaster
from app.services.resume_service import MAX_RESUME_BYTES
from app.tests.fixtures.pdf_bytes import (
    HTML_MASQUERADING_AS_PDF,
    MINIMAL_PDF,
    NOT_A_PDF,
    pdf_of_size,
)

REGISTER = "/api/v1/auth/register"
RESUMES = "/api/v1/resumes"

PASSWORD = "correct horse battery"


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload_args(content: bytes, name: str = "resume.pdf") -> dict[str, object]:
    return {"files": {"file": (name, content, "application/pdf")}}


async def test_a_non_pdf_is_rejected(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")

    response = await client.post(RESUMES, headers=headers, **_upload_args(NOT_A_PDF))  # type: ignore[arg-type]

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_resume_format"


async def test_a_file_renamed_to_pdf_is_rejected(client: AsyncClient) -> None:
    """Content is identified by its bytes, not its name.

    The realistic version of this is a student who saved a login page or a Word
    document and renamed it. The declared content type is equally untrustworthy —
    the request below claims application/pdf.
    """
    headers = await _auth(client, "ada@example.com")

    response = await client.post(
        RESUMES,
        headers=headers,
        **_upload_args(HTML_MASQUERADING_AS_PDF, name="my-resume.pdf"),  # type: ignore[arg-type]
    )

    assert response.status_code == 415


async def test_an_empty_file_is_rejected(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")

    response = await client.post(RESUMES, headers=headers, **_upload_args(b""))  # type: ignore[arg-type]

    assert response.status_code == 415


async def test_a_file_over_the_size_cap_is_rejected(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")
    oversized = pdf_of_size(MAX_RESUME_BYTES + 1024)

    response = await client.post(RESUMES, headers=headers, **_upload_args(oversized))  # type: ignore[arg-type]

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "resume_too_large"


async def test_a_file_at_the_size_cap_is_accepted(client: AsyncClient) -> None:
    """The boundary is inclusive, so the limit stated to the student is the real one."""
    headers = await _auth(client, "ada@example.com")

    response = await client.post(
        RESUMES,
        headers=headers,
        **_upload_args(pdf_of_size(MAX_RESUME_BYTES)),  # type: ignore[arg-type]
    )

    assert response.status_code == 201


async def test_a_rejected_upload_stores_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await _auth(client, "ada@example.com")

    await client.post(RESUMES, headers=headers, **_upload_args(NOT_A_PDF))  # type: ignore[arg-type]

    stored = await session.scalar(select(func.count()).select_from(ResumeMaster))
    assert stored == 0


async def test_a_rejected_upload_leaves_the_active_resume_untouched(
    client: AsyncClient,
) -> None:
    """The failure that would be worst to ship.

    If a rejected upload deactivated the previous version, the student would keep a
    resume they can see in the list but that nothing uses, and no error would say so.
    """
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args(MINIMAL_PDF))  # type: ignore[arg-type]

    await client.post(RESUMES, headers=headers, **_upload_args(NOT_A_PDF))  # type: ignore[arg-type]

    listed = (await client.get(RESUMES, headers=headers)).json()
    assert len(listed) == 1
    assert listed[0]["version"] == 1
    assert listed[0]["is_active"] is True


async def test_a_rejected_upload_does_not_consume_a_version_number(
    client: AsyncClient,
) -> None:
    """Version numbers are shown to the student, so a gap is a question they cannot answer."""
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args(MINIMAL_PDF))  # type: ignore[arg-type]
    await client.post(RESUMES, headers=headers, **_upload_args(NOT_A_PDF))  # type: ignore[arg-type]

    accepted = await client.post(RESUMES, headers=headers, **_upload_args(MINIMAL_PDF))  # type: ignore[arg-type]

    assert accepted.json()["version"] == 2
