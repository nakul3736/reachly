"""Seeding the documented demo account.

Rule 17 requires judges to be given working credentials, and Round One screening rewards
a project that works on first contact. The properties that matter are that seeding can be
run repeatedly — a redeploy will run it again — and that it cannot damage anything it did
not create.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import ResumeMaster
from app.models.student import Student
from app.models.user import User
from app.seed import DemoCredentialsMissing, seed_demo_student

LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"
PROFILE = "/api/v1/students/me"
PARSED = "/api/v1/resumes/parsed"

DEMO_EMAIL = "demo@reachly.app"
DEMO_PASSWORD = "reachly-demo-2026"


@pytest.fixture(autouse=True)
def _demo_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_STUDENT_EMAIL", DEMO_EMAIL)
    monkeypatch.setenv("DEMO_STUDENT_PASSWORD", DEMO_PASSWORD)
    from app.config import get_settings

    get_settings.cache_clear()


async def test_the_seeded_credentials_can_log_in(
    client: AsyncClient, session: AsyncSession
) -> None:
    await seed_demo_student(session)

    response = await client.post(LOGIN, json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})

    assert response.status_code == 200


async def test_the_seeded_profile_is_complete_enough_for_results(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A judge should land on a populated product, not a form.

    `missing_for_results` being empty is the same check the feed uses to decide whether
    it can produce anything, so this asserts the account is actually usable rather than
    merely present.
    """
    await seed_demo_student(session)
    token = (
        await client.post(LOGIN, json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    ).json()["access_token"]

    profile = (
        await client.get(PROFILE, headers={"Authorization": f"Bearer {token}"})
    ).json()

    assert profile["missing_for_results"] == []
    assert profile["target_role"]
    assert profile["locations"]
    assert profile["skills"]
    assert profile["years_experience"] is not None


async def test_the_seeded_student_has_a_parsed_active_resume(
    client: AsyncClient, session: AsyncSession
) -> None:
    await seed_demo_student(session)
    token = (
        await client.post(LOGIN, json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    ).json()["access_token"]

    parsed = await client.get(PARSED, headers={"Authorization": f"Bearer {token}"})

    assert parsed.status_code == 200
    body = parsed.json()
    assert body["experience"]
    assert [b["id"] for e in body["experience"] for b in e["bullets"]]


async def test_seeding_twice_creates_one_account(session: AsyncSession) -> None:
    """A redeploy runs the seed again.

    If that produced a second account the unique email constraint would fail the deploy,
    and if it produced a second resume version the demo would drift every release.
    """
    await seed_demo_student(session)
    await seed_demo_student(session)

    users = await session.scalar(
        select(func.count()).select_from(User).where(User.email == DEMO_EMAIL)
    )
    students = await session.scalar(select(func.count()).select_from(Student))
    assert users == 1
    assert students == 1


async def test_seeding_twice_does_not_add_a_resume_version(session: AsyncSession) -> None:
    await seed_demo_student(session)
    await seed_demo_student(session)

    versions = await session.scalar(select(func.count()).select_from(ResumeMaster))
    assert versions == 1


async def test_seeding_refuses_without_a_configured_password(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No default password, ever.

    A hardcoded fallback would ship a known credential to every deployment that forgot
    to set one, including any that later holds a real user's data.
    """
    monkeypatch.delenv("DEMO_STUDENT_PASSWORD", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(DemoCredentialsMissing):
        await seed_demo_student(session)


async def test_seeding_leaves_other_accounts_untouched(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Safe to run against a database holding real data.

    The seed touches one documented account. It must never reset, truncate, or
    reactivate anything belonging to anyone else.
    """
    real = {"email": "real@example.com", "password": "a real password"}
    await client.post(REGISTER, json=real)
    token = (await client.post(LOGIN, json=real)).json()["access_token"]
    await client.patch(
        PROFILE,
        headers={"Authorization": f"Bearer {token}"},
        json={"target_role": "Data Engineer", "skills": ["Scala"]},
    )

    await seed_demo_student(session)

    profile = (
        await client.get(PROFILE, headers={"Authorization": f"Bearer {token}"})
    ).json()
    assert profile["target_role"] == "Data Engineer"
    assert profile["skills"] == ["Scala"]


async def test_seeding_reports_what_it_did(session: AsyncSession) -> None:
    """The command is run by a human during deploy, so it says what happened.

    Silence after a deploy step leaves you unable to tell success from a no-op.
    """
    first = await seed_demo_student(session)
    second = await seed_demo_student(session)

    assert first.created is True
    assert second.created is False
