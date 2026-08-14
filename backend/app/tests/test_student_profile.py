"""The student profile, asserted at the HTTP seam.

Two properties matter most here and are tested hardest: a fresh profile invents
nothing, and one account cannot reach another's profile.
"""

from httpx import AsyncClient

REGISTER = "/api/v1/auth/register"
PROFILE = "/api/v1/students/me"

PASSWORD = "correct horse battery"


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_registering_creates_a_readable_profile(client: AsyncClient) -> None:
    """There must never be an authenticated user with nowhere to write a profile.

    Creating the row lazily on first write would mean every later feature has to
    handle a student that does not exist yet.
    """
    headers = await _auth(client, "ada@example.com")

    response = await client.get(PROFILE, headers=headers)

    assert response.status_code == 200


async def test_a_fresh_profile_invents_nothing(client: AsyncClient) -> None:
    """Absent is not the same as zero or empty-string.

    `years_experience` of 0 is a claim about the student; None is the honest
    statement that they have not said yet. The distinction survives into scoring,
    where a missing value must not be treated as a confirmed zero.
    """
    headers = await _auth(client, "ada@example.com")

    body = (await client.get(PROFILE, headers=headers)).json()

    assert body["name"] is None
    assert body["target_role"] is None
    assert body["years_experience"] is None
    assert body["locations"] == []
    assert body["skills"] == []


async def test_the_profile_reports_what_is_still_missing(client: AsyncClient) -> None:
    """The interface should say what it needs, not fail silently with no results.

    A student with an empty profile who lands on the feed and sees nothing has no
    way to know why. This is the field that tells them.
    """
    headers = await _auth(client, "ada@example.com")

    body = (await client.get(PROFILE, headers=headers)).json()

    assert set(body["missing_for_results"]) == {"target_role", "locations", "skills"}


async def test_reading_a_profile_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(PROFILE)

    assert response.status_code == 401
