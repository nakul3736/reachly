"""Updating the student profile.

The two properties tested hardest: a partial update cannot silently clear fields it
did not mention, and one account cannot reach another's profile.
"""

import pytest
from httpx import AsyncClient

REGISTER = "/api/v1/auth/register"
PROFILE = "/api/v1/students/me"

PASSWORD = "correct horse battery"


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_update_sets_the_supplied_fields(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")

    response = await client.patch(
        PROFILE,
        headers=headers,
        json={
            "name": "Ada Lovelace",
            "target_role": "Backend Engineer",
            "years_experience": 1,
            "locations": ["Toronto, ON", "Remote"],
            "skills": ["Python", "PostgreSQL"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Ada Lovelace"
    assert body["target_role"] == "Backend Engineer"
    assert body["years_experience"] == 1
    assert body["locations"] == ["Toronto, ON", "Remote"]
    assert body["skills"] == ["Python", "PostgreSQL"]


async def test_update_persists(client: AsyncClient) -> None:
    """Read it back on a separate request, not just from the update response."""
    headers = await _auth(client, "ada@example.com")
    await client.patch(PROFILE, headers=headers, json={"target_role": "Backend Engineer"})

    body = (await client.get(PROFILE, headers=headers)).json()

    assert body["target_role"] == "Backend Engineer"


async def test_a_partial_update_leaves_other_fields_alone(client: AsyncClient) -> None:
    """Editing one field must not clear the rest.

    The failure this guards against is a form that submits only the field the
    student touched and wipes everything else.
    """
    headers = await _auth(client, "ada@example.com")
    await client.patch(
        PROFILE,
        headers=headers,
        json={
            "name": "Ada Lovelace",
            "target_role": "Backend Engineer",
            "years_experience": 1,
            "locations": ["Toronto, ON"],
            "skills": ["Python"],
        },
    )

    await client.patch(PROFILE, headers=headers, json={"target_role": "Data Engineer"})

    body = (await client.get(PROFILE, headers=headers)).json()
    assert body["target_role"] == "Data Engineer"
    assert body["name"] == "Ada Lovelace"
    assert body["years_experience"] == 1
    assert body["locations"] == ["Toronto, ON"]
    assert body["skills"] == ["Python"]


async def test_an_empty_update_changes_nothing(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")
    await client.patch(PROFILE, headers=headers, json={"name": "Ada Lovelace"})

    response = await client.patch(PROFILE, headers=headers, json={})

    assert response.status_code == 200
    assert response.json()["name"] == "Ada Lovelace"


async def test_multiple_locations_are_supported(client: AsyncClient) -> None:
    """A student searching one city and remote roles together is the normal case."""
    headers = await _auth(client, "ada@example.com")

    response = await client.patch(
        PROFILE, headers=headers, json={"locations": ["Toronto, ON", "Vancouver, BC", "Remote"]}
    )

    assert response.json()["locations"] == ["Toronto, ON", "Vancouver, BC", "Remote"]


@pytest.mark.parametrize("years", [-1, -50, 100, 61])
async def test_implausible_years_of_experience_is_rejected(
    client: AsyncClient, years: int
) -> None:
    headers = await _auth(client, "ada@example.com")

    response = await client.patch(PROFILE, headers=headers, json={"years_experience": years})

    assert response.status_code == 422


@pytest.mark.parametrize("years", [0, 1, 5])
async def test_plausible_years_of_experience_is_accepted(
    client: AsyncClient, years: int
) -> None:
    """Zero is a legitimate answer for a new graduate, and distinct from unstated."""
    headers = await _auth(client, "ada@example.com")

    response = await client.patch(PROFILE, headers=headers, json={"years_experience": years})

    assert response.status_code == 200
    assert response.json()["years_experience"] == years


async def test_blank_entries_are_dropped_from_lists(client: AsyncClient) -> None:
    """A stored empty string becomes a filter that matches nothing.

    Worse, it does so silently — the student sees an empty feed and no reason for it.
    """
    headers = await _auth(client, "ada@example.com")

    response = await client.patch(
        PROFILE,
        headers=headers,
        json={"locations": ["", "   ", "Toronto, ON"], "skills": ["Python", "  ", ""]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["locations"] == ["Toronto, ON"]
    assert body["skills"] == ["Python"]


async def test_list_entries_are_trimmed(client: AsyncClient) -> None:
    headers = await _auth(client, "ada@example.com")

    response = await client.patch(PROFILE, headers=headers, json={"skills": ["  Python  "]})

    assert response.json()["skills"] == ["Python"]


async def test_duplicate_list_entries_are_collapsed(client: AsyncClient) -> None:
    """Case-insensitively, keeping the spelling the student chose."""
    headers = await _auth(client, "ada@example.com")

    response = await client.patch(
        PROFILE, headers=headers, json={"skills": ["Python", "python", "PYTHON"]}
    )

    assert response.json()["skills"] == ["Python"]


async def test_missing_for_results_shrinks_as_the_profile_is_filled(
    client: AsyncClient,
) -> None:
    headers = await _auth(client, "ada@example.com")

    after_role = await client.patch(
        PROFILE, headers=headers, json={"target_role": "Backend Engineer"}
    )
    assert set(after_role.json()["missing_for_results"]) == {"locations", "skills"}

    complete = await client.patch(
        PROFILE, headers=headers, json={"locations": ["Remote"], "skills": ["Python"]}
    )
    assert complete.json()["missing_for_results"] == []


async def test_updating_a_profile_requires_authentication(client: AsyncClient) -> None:
    response = await client.patch(PROFILE, json={"target_role": "Backend Engineer"})

    assert response.status_code == 401


async def test_one_student_cannot_see_another_profile(client: AsyncClient) -> None:
    ada = await _auth(client, "ada@example.com")
    grace = await _auth(client, "grace@example.com")

    await client.patch(PROFILE, headers=ada, json={"name": "Ada Lovelace"})
    await client.patch(PROFILE, headers=grace, json={"name": "Grace Hopper"})

    assert (await client.get(PROFILE, headers=ada)).json()["name"] == "Ada Lovelace"
    assert (await client.get(PROFILE, headers=grace)).json()["name"] == "Grace Hopper"


async def test_one_student_cannot_modify_another_profile(client: AsyncClient) -> None:
    """There is no id in the path, so the token is the only thing selecting a row."""
    ada = await _auth(client, "ada@example.com")
    grace = await _auth(client, "grace@example.com")
    await client.patch(PROFILE, headers=ada, json={"skills": ["Python"]})

    await client.patch(PROFILE, headers=grace, json={"skills": ["Fortran"]})

    assert (await client.get(PROFILE, headers=ada)).json()["skills"] == ["Python"]
