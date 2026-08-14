"""Parsing on upload, and reading the structured result back.

The identifiers asserted here are what `provenance_map` will reference in ADR 0006, so
they have to survive the round trip through the database — not merely exist in memory at
parse time.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import ResumeMaster
from app.tests.fixtures.pdf_bytes import RECORDED_RESUME_PDF

REGISTER = "/api/v1/auth/register"
RESUMES = "/api/v1/resumes"
PARSED = "/api/v1/resumes/parsed"

PASSWORD = "correct horse battery"


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload_args(content: bytes = RECORDED_RESUME_PDF) -> dict[str, object]:
    return {"files": {"file": ("resume.pdf", content, "application/pdf")}}


async def test_upload_stores_the_parsed_result(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await _auth(client, "ada@example.com")

    await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]

    stored = (await session.execute(select(ResumeMaster))).scalar_one()
    assert stored.parsed_json is not None
    assert stored.parsed_json["experience"]


async def test_the_parsed_active_resume_can_be_read(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]

    response = await client.get(PARSED, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["experience"]
    assert body["skills"]


async def test_bullet_identifiers_survive_the_database_round_trip(
    client: AsyncClient,
) -> None:
    """The provenance reference has to exist on the way out, not just at parse time.

    A bullet id lost in serialisation would leave `provenance_map` pointing at nothing,
    and the failure would only appear when a tailored bullet was checked against its
    source.
    """
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]

    body = (await client.get(PARSED, headers=headers)).json()

    bullet_ids = [b["id"] for e in body["experience"] for b in e["bullets"]]
    assert bullet_ids
    assert all(bullet_ids)
    assert len(set(bullet_ids)) == len(bullet_ids)


async def test_the_parsed_result_keeps_dates_as_written(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]

    body = (await client.get(PARSED, headers=headers)).json()

    assert "January 2026 - Present" in [entry["dates"] for entry in body["experience"]]


async def test_the_parsed_result_retains_the_full_text(client: AsyncClient) -> None:
    """The ADR 0006 validator draws its entity set from the whole document."""
    headers = await _auth(client, "ada@example.com")
    await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]

    body = (await client.get(PARSED, headers=headers)).json()

    assert body["raw_text"]


async def test_a_specific_version_can_be_parsed_and_read(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")
    first = await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]
    first_id = first.json()["id"]
    await client.post(RESUMES, headers=headers, **_upload_args())  # type: ignore[arg-type]

    response = await client.get(f"{RESUMES}/{first_id}/parsed", headers=headers)

    assert response.status_code == 200
    assert response.json()["experience"]


async def test_reading_a_parsed_resume_with_none_uploaded_is_a_clear_error(
    client: AsyncClient,
) -> None:
    """Not an empty resume.

    A student who has uploaded nothing and a student whose resume parsed to nothing are
    in different situations and need different guidance.
    """
    headers = await _auth(client, "ada@example.com")

    response = await client.get(PARSED, headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_active_resume"


async def test_reading_a_parsed_resume_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(PARSED)

    assert response.status_code == 401


async def test_one_student_cannot_read_another_parsed_resume(client: AsyncClient) -> None:
    ada = await _auth(client, "ada@example.com")
    grace = await _auth(client, "grace@example.com")
    created = await client.post(RESUMES, headers=ada, **_upload_args())  # type: ignore[arg-type]
    resume_id = created.json()["id"]

    # Assert the owner can read it first. Without this the test passes against a route
    # that does not exist, since a missing route also answers 404.
    assert (await client.get(f"{RESUMES}/{resume_id}/parsed", headers=ada)).status_code == 200

    response = await client.get(f"{RESUMES}/{resume_id}/parsed", headers=grace)

    assert response.status_code == 404
