"""Login and token handling, asserted at the HTTP seam.

The central property here: a failed login must not reveal whether the email exists.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.config import get_settings

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"

EMAIL = "ada@example.com"
PASSWORD = "correct horse battery"


async def _register(client: AsyncClient, email: str = EMAIL) -> str:
    response = await client.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return str(response.json()["access_token"])


async def test_login_with_correct_credentials_returns_a_token(client: AsyncClient) -> None:
    await _register(client)

    response = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_is_case_insensitive_on_email(client: AsyncClient) -> None:
    await _register(client)

    response = await client.post(LOGIN, json={"email": "ADA@Example.com", "password": PASSWORD})

    assert response.status_code == 200


async def test_unknown_email_and_wrong_password_are_indistinguishable(
    client: AsyncClient,
) -> None:
    """The property that stops account enumeration.

    If these two responses differ in any way a caller can observe, submitting one
    request tells them whether a given person has an account here.
    """
    await _register(client)

    wrong_password = await client.post(LOGIN, json={"email": EMAIL, "password": "wrong pass!!"})
    unknown_email = await client.post(
        LOGIN, json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_me_returns_the_current_user_with_a_valid_token(client: AsyncClient) -> None:
    token = await _register(client)

    response = await client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


async def test_me_never_exposes_credential_columns(client: AsyncClient) -> None:
    token = await _register(client)

    response = await client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert "password_hash" not in body
    assert "password_reset_token" not in body


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "not-a-scheme",
        "Bearer",
        "Bearer ",
        "Bearer not.a.jwt",
        "Basic abc123",
    ],
    ids=[
        "absent",
        "empty",
        "no-scheme",
        "scheme-only",
        "scheme-and-space",
        "malformed-token",
        "wrong-scheme",
    ],
)
async def test_me_rejects_a_bad_authorization_header(
    client: AsyncClient, header: str | None
) -> None:
    headers = {} if header is None else {"Authorization": header}

    response = await client.get(ME, headers=headers)

    assert response.status_code == 401


async def test_me_rejects_a_token_signed_with_another_key(client: AsyncClient) -> None:
    await _register(client)
    forged = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "a-different-secret",
        algorithm="HS256",
    )

    response = await client.get(ME, headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


async def test_me_rejects_an_expired_token(client: AsyncClient) -> None:
    await _register(client)
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) - timedelta(seconds=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )

    response = await client.get(ME, headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


async def test_me_rejects_a_token_naming_a_user_that_does_not_exist(
    client: AsyncClient,
) -> None:
    """A validly signed token is not sufficient; the subject must still exist."""
    orphan = jwt.encode(
        {"sub": "999999", "exp": datetime.now(UTC) + timedelta(hours=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )

    response = await client.get(ME, headers={"Authorization": f"Bearer {orphan}"})

    assert response.status_code == 401
