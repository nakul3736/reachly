"""The public job feed.

Public deliberately: story 1 is the first thing a visitor should be able to do, and requiring
an account to find out whether the product has any jobs is why people leave.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job

pytestmark = pytest.mark.anyio


async def _add(session: AsyncSession, **overrides: object) -> Job:
    values: dict[str, object] = {
        "source": "greenhouse",
        "source_job_id": str(overrides.pop("n", 1)),
        "company_name": "Acme",
        "title": "Software Engineer",
        "location_raw": "Toronto, Ontario, Canada",
        "description": "Build things carefully.",
        "apply_url": "https://example.com/1",
        "is_verified": True,
    }
    values.update(overrides)
    job = Job(**values)
    session.add(job)
    await session.commit()
    return job


async def test_the_feed_needs_no_account(client: AsyncClient, session: AsyncSession) -> None:
    await _add(session, n=1)

    response = await client.get("/api/v1/jobs")

    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_the_feed_reports_a_total_so_filters_can_be_widened(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Story 15 — a count is what tells a student whether to relax a filter."""
    for i in range(3):
        await _add(session, n=i, title=f"Engineer {i}")

    payload = (await client.get("/api/v1/jobs")).json()

    assert payload["total"] == 3
    assert len(payload["items"]) == 3


async def test_a_closed_job_is_not_in_the_feed(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The rule the whole product rests on — no applying to roles that are already gone."""
    await _add(session, n=1, title="Open Role")
    await _add(session, n=2, title="Filled Role", closed_at=datetime.now(UTC))

    payload = (await client.get("/api/v1/jobs")).json()

    assert payload["total"] == 1
    assert [item["title"] for item in payload["items"]] == ["Open Role"]


async def test_an_alias_is_not_its_own_feed_row(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Ticket 06 collapses duplicates by pointing one row at another.

    The feed has to honour that, or dedup would run correctly and change nothing a student
    sees.
    """
    canonical = await _add(session, n=1, title="Canonical")
    await _add(session, n=2, source="muse", title="Syndicated Copy", is_verified=False)
    alias = (await client.get("/api/v1/jobs")).json()["items"]
    assert len(alias) == 2

    copy = await _add(session, n=3, source="lever", title="Another Copy")
    copy.canonical_job_id = canonical.id
    await session.commit()

    titles = [item["title"] for item in (await client.get("/api/v1/jobs")).json()["items"]]

    assert "Another Copy" not in titles


async def test_the_newest_jobs_come_first(
    client: AsyncClient, session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    await _add(session, n=1, title="Older", posted_at=now - timedelta(days=10))
    await _add(session, n=2, title="Newer", posted_at=now - timedelta(days=1))

    titles = [item["title"] for item in (await client.get("/api/v1/jobs")).json()["items"]]

    assert titles == ["Newer", "Older"]


async def test_the_feed_is_paginated(client: AsyncClient, session: AsyncSession) -> None:
    """Story 17 — two thousand matches must not arrive in one response."""
    for i in range(5):
        await _add(session, n=i, title=f"Role {i}")

    payload = (await client.get("/api/v1/jobs?page=1&page_size=2")).json()

    assert payload["total"] == 5
    assert len(payload["items"]) == 2
    assert payload["page"] == 1

    second = (await client.get("/api/v1/jobs?page=2&page_size=2")).json()
    assert len(second["items"]) == 2
    first_ids = {item["id"] for item in payload["items"]}
    assert not first_ids & {item["id"] for item in second["items"]}


async def test_the_feed_says_whether_a_posting_is_company_confirmed(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Story 9. `confirmed` and `inferred` are functionally different claims.

    A posting on a company's own board and one seen only on an aggregator are not the same
    thing, and the feed must not present them identically.
    """
    await _add(session, n=1, title="From Board", is_verified=True)
    await _add(session, n=2, source="muse", title="From Aggregator", is_verified=False)

    items = {i["title"]: i for i in (await client.get("/api/v1/jobs")).json()["items"]}

    assert items["From Board"]["is_verified"] is True
    assert items["From Aggregator"]["is_verified"] is False
    assert items["From Aggregator"]["source"] == "muse"


async def test_a_single_job_carries_its_full_description(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Story 10 — deciding whether to apply should not require opening six tabs."""
    long_description = ("A real description. " * 200).strip()
    job = await _add(session, n=1, description=long_description)

    payload = (await client.get(f"/api/v1/jobs/{job.id}")).json()

    assert payload["description"] == long_description
    assert payload["apply_url"] == "https://example.com/1"


async def test_a_closed_job_is_still_retrievable_and_says_so(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Story 29, and kindness to anyone who bookmarked it.

    404 would be a lie: the job existed and the student may have applied to it.
    """
    closed_at = datetime.now(UTC)
    job = await _add(session, n=1, closed_at=closed_at)

    response = await client.get(f"/api/v1/jobs/{job.id}")

    assert response.status_code == 200
    assert response.json()["closed_at"] is not None


async def test_an_unknown_job_is_a_clean_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/jobs/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"
