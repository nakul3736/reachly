"""What happens when a resume cannot be read.

The requirement being tested is that the student is told *which* problem occurred. A
scan they can fix by re-exporting; a structuring failure they cannot fix at all. One
generic error would leave them retrying the wrong thing.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.resume_parser import ResumeParseFailed
from app.domain.parsed_resume import ParsedResume
from app.models.resume import ResumeMaster
from app.tests.fixtures.pdf_bytes import MINIMAL_PDF, NOT_A_PDF, RECORDED_RESUME_PDF

REGISTER = "/api/v1/auth/register"
RESUMES = "/api/v1/resumes"

PASSWORD = "correct horse battery"


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload_args(content: bytes) -> dict[str, object]:
    return {"files": {"file": ("resume.pdf", content, "application/pdf")}}


async def test_a_pdf_with_no_text_layer_is_refused_as_unreadable(client: AsyncClient) -> None:
    """What a scanned resume does.

    The file is a real PDF, so it passes the format check. It simply has no text, which
    is a different problem with different advice.
    """
    headers = await _auth(client, "ada@example.com")

    response = await client.post(RESUMES, headers=headers, **_upload_args(MINIMAL_PDF))  # type: ignore[arg-type]

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "resume_unreadable"


async def test_unreadable_is_distinguished_from_the_wrong_file_type(
    client: AsyncClient,
) -> None:
    """Three different problems must not collapse into one message.

    A .docx renamed to .pdf, and a scan, need different things from the student. A
    single "could not read your resume" would leave both retrying the wrong fix.
    """
    headers = await _auth(client, "ada@example.com")

    wrong_type = await client.post(RESUMES, headers=headers, **_upload_args(NOT_A_PDF))  # type: ignore[arg-type]
    no_text = await client.post(RESUMES, headers=headers, **_upload_args(MINIMAL_PDF))  # type: ignore[arg-type]

    assert wrong_type.json()["error"]["code"] == "unsupported_resume_format"
    assert no_text.json()["error"]["code"] == "resume_unreadable"
    assert wrong_type.status_code != no_text.status_code


async def test_an_unreadable_upload_stores_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A failed parse must not create a version.

    Otherwise the student has an active resume containing nothing, and tailoring draws
    on no evidence while appearing to work.
    """
    headers = await _auth(client, "ada@example.com")

    await client.post(RESUMES, headers=headers, **_upload_args(MINIMAL_PDF))  # type: ignore[arg-type]

    count = await session.scalar(select(func.count()).select_from(ResumeMaster))
    assert count == 0


async def test_an_unreadable_upload_leaves_the_active_version_untouched(
    client: AsyncClient,
) -> None:
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args(RECORDED_RESUME_PDF))  # type: ignore[arg-type]

    await client.post(RESUMES, headers=headers, **_upload_args(MINIMAL_PDF))  # type: ignore[arg-type]

    listed = (await client.get(RESUMES, headers=headers)).json()
    assert len(listed) == 1
    assert listed[0]["version"] == 1
    assert listed[0]["is_active"] is True


async def test_the_unreadable_message_tells_the_student_what_to_do(
    client: AsyncClient,
) -> None:
    """The remedy is actionable, and does not blame something they cannot change."""
    headers = await _auth(client, "ada@example.com")

    response = await client.post(RESUMES, headers=headers, **_upload_args(MINIMAL_PDF))  # type: ignore[arg-type]

    message = response.json()["error"]["message"].lower()
    assert "export" in message


async def test_a_structuring_failure_is_reported_separately(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Text was read but could not be structured.

    Not the student's fault and not fixable by them, so it must not be reported as a
    problem with their file. Forced here because the fixture parser cannot fail this way
    on its own — and an error path with no test is an error path that has never run.
    """

    class FailingParser:
        async def parse(self, pdf_bytes: bytes) -> ParsedResume:
            raise ResumeParseFailed

    monkeypatch.setattr("app.api.resumes.get_resume_parser", lambda: FailingParser())
    headers = await _auth(client, "ada@example.com")

    response = await client.post(RESUMES, headers=headers, **_upload_args(RECORDED_RESUME_PDF))  # type: ignore[arg-type]

    assert response.json()["error"]["code"] == "resume_parse_failed"
    assert response.status_code != 422


async def test_a_structuring_failure_stores_nothing(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingParser:
        async def parse(self, pdf_bytes: bytes) -> ParsedResume:
            raise ResumeParseFailed

    monkeypatch.setattr("app.api.resumes.get_resume_parser", lambda: FailingParser())
    headers = await _auth(client, "ada@example.com")

    await client.post(RESUMES, headers=headers, **_upload_args(RECORDED_RESUME_PDF))  # type: ignore[arg-type]

    count = await session.scalar(select(func.count()).select_from(ResumeMaster))
    assert count == 0
