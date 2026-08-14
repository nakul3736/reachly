"""Registration and login, asserted at the HTTP seam.

Login failure is deliberately indistinguishable between an unknown email and a wrong
password, so that whether someone has an account here cannot be discovered by probing.
"""

import pytest
from httpx import AsyncClient

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


async def test_register_returns_a_token(client: AsyncClient) -> None:
    """A new student is logged in by registering.

    Asking someone to log in immediately after signing up is friction with no
    security benefit.
    """
    response = await client.post(
        REGISTER, json={"email": "ada@example.com", "password": "correct horse battery"}
    )

    assert response.status_code == 201
    assert response.json()["access_token"]


async def test_register_never_returns_the_password_hash(client: AsyncClient) -> None:
    response = await client.post(
        REGISTER, json={"email": "ada@example.com", "password": "correct horse battery"}
    )

    # Assert success first: a 404 body contains neither word, so without this the
    # test would pass against a route that does not exist.
    assert response.status_code == 201
    body = response.text.lower()
    assert "hash" not in body
    assert "password" not in body


async def test_register_lowercases_the_email(client: AsyncClient) -> None:
    """Case must not create a second account for the same person."""
    await client.post(
        REGISTER, json={"email": "Ada@Example.COM", "password": "correct horse battery"}
    )

    duplicate = await client.post(
        REGISTER, json={"email": "ada@example.com", "password": "correct horse battery"}
    )

    assert duplicate.status_code == 409


async def test_registering_an_existing_email_is_actionable(client: AsyncClient) -> None:
    """The student should be told to log in, not left guessing."""
    await client.post(
        REGISTER, json={"email": "ada@example.com", "password": "correct horse battery"}
    )

    duplicate = await client.post(
        REGISTER, json={"email": "ada@example.com", "password": "correct horse battery"}
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_already_registered"


@pytest.mark.parametrize("password", ["", "short", "1234567"])
async def test_register_rejects_a_password_below_the_minimum(
    client: AsyncClient, password: str
) -> None:
    response = await client.post(
        REGISTER, json={"email": "ada@example.com", "password": password}
    )

    assert response.status_code == 422


@pytest.mark.parametrize("email", ["not-an-email", "@example.com", "ada@", ""])
async def test_register_rejects_a_malformed_email(client: AsyncClient, email: str) -> None:
    response = await client.post(
        REGISTER, json={"email": email, "password": "correct horse battery"}
    )

    assert response.status_code == 422
