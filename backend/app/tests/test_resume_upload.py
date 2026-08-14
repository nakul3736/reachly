"""Resume upload and listing, asserted at the HTTP seam.

Parsing is deliberately out of scope here. This proves the bytes survive a round trip
and that versions are listed, before parsing complicates either.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import ResumeMaster
from app.tests.fixtures.pdf_bytes import MINIMAL_PDF

REGISTER = "/api/v1/auth/register"
RESUMES = "/api/v1/resumes"

PASSWORD = "correct horse battery"


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload_args(content: bytes = MINIMAL_PDF, name: str = "resume.pdf") -> dict[str, object]:
    return {"files": {"file": (name, content, "application/pdf")}}


async def test_uploading_a_pdf_is_accepted(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")

    response = await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]

    assert response.status_code == 201
    assert response.json()["version"] == 1


async def test_a_new_student_has_no_resumes(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")

    response = await client.get(RESUMES, headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_an_uploaded_resume_is_listed(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args(name="ada-cv.pdf"))  # type: ignore[arg-type]

    listed = (await client.get(RESUMES, headers=headers)).json()

    assert len(listed) == 1
    assert listed[0]["version"] == 1
    assert listed[0]["filename"] == "ada-cv.pdf"
    assert listed[0]["is_active"] is True
    assert listed[0]["uploaded_at"]


async def test_the_listing_never_includes_the_file_bytes(client: AsyncClient) -> None:
    """A resume list is rendered on every visit to the profile screen.

    Returning megabytes of base64 alongside the metadata would make that screen
    slow for no benefit, and the bytes are separately downloadable.
    """
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]

    listed = (await client.get(RESUMES, headers=headers)).json()

    assert "pdf_bytes" not in listed[0]
    assert "content" not in listed[0]


async def test_the_original_bytes_are_stored_in_postgres(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Not on the filesystem.

    Free hosting has an ephemeral disk, so a redeploy would silently destroy every
    upload — the student would not find out until they tried to tailor a resume.
    Asserted against the row rather than through the API, because storing a path
    that happens to work in development is exactly the bug this guards against.
    """
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]

    stored = (await session.execute(select(ResumeMaster))).scalar_one()

    assert stored.pdf_bytes == MINIMAL_PDF
    assert stored.byte_size == len(MINIMAL_PDF)


async def test_the_original_file_can_be_downloaded_unchanged(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")
    created = await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]
    resume_id = created.json()["id"]

    response = await client.get(f"{RESUMES}/{resume_id}/file", headers=headers)

    assert response.status_code == 200
    assert response.content == MINIMAL_PDF
    assert response.headers["content-type"] == "application/pdf"


async def test_uploading_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(RESUMES, **_upload_args())  # type: ignore[arg-type]

    assert response.status_code == 401


async def test_listing_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(RESUMES)

    assert response.status_code == 401


async def test_one_student_cannot_list_another_students_resumes(client: AsyncClient) -> None:
    ada = await _auth(client, "ada@example.com")
    grace = await _auth(client, "grace@example.com")
    await client.post(RESUMES, headers=ada, **_upload_args())  # type: ignore[arg-type]

    listed = (await client.get(RESUMES, headers=grace)).json()

    assert listed == []


async def test_one_student_cannot_download_another_students_resume(
    client: AsyncClient,
) -> None:
    """The id is guessable, so this is the case ownership has to be checked on."""
    ada = await _auth(client, "ada@example.com")
    grace = await _auth(client, "grace@example.com")
    created = await client.post(RESUMES, headers=ada, **_upload_args())  # type: ignore[arg-type]
    resume_id = created.json()["id"]

    response = await client.get(f"{RESUMES}/{resume_id}/file", headers=grace)

    assert response.status_code == 404
