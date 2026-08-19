"""Filtering the feed, and where classification happens.

The filters are hard exclusions rather than re-orderings. Location was settled as a hard filter
in ADR 0003, and the same reasoning applies to seniority: a role wanting ten years is not a
worse match for a graduating student, it is not a match.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.services.job_service import classify_stored_jobs

pytestmark = pytest.mark.anyio


async def _add(session: AsyncSession, n: int, title: str, location: str | None = None) -> Job:
    job = Job(
        source="greenhouse",
        source_job_id=str(n),
        company_name="Acme",
        title=title,
        location_raw=location,
        description=f"About {title}.",
        apply_url=f"https://example.com/{n}",
        is_verified=True,
    )
    session.add(job)
    await session.commit()
    return job


async def _titles(client: AsyncClient, query: str) -> list[str]:
    response = await client.get(f"/api/v1/jobs?{query}")
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


# --- classification happens without re-fetching ---------------------------------------


async def test_stored_jobs_can_be_classified_without_refetching(
    session: AsyncSession,
) -> None:
    """A rule fix must be applicable to the index we already have.

    Otherwise every correction to the classifier costs a full refresh of every board, which on
    a free host is an hour we do not have and a burst of provider requests we should not make.
    """
    await _add(session, 1, "Senior Software Engineer", "San Francisco, CA")
    await _add(session, 2, "Software Engineer Intern", "Toronto, ON")

    updated = await classify_stored_jobs(session)

    assert updated == 2
    rows = {j.title: j for j in (await session.execute(select(Job))).scalars()}
    assert rows["Senior Software Engineer"].seniority == "senior"
    assert rows["Senior Software Engineer"].role_family == "software_engineering"
    assert rows["Senior Software Engineer"].country == "US"
    assert rows["Software Engineer Intern"].seniority == "entry"
    assert rows["Software Engineer Intern"].country == "CA"


async def test_classifying_twice_changes_nothing_the_second_time(
    session: AsyncSession,
) -> None:
    await _add(session, 1, "Data Scientist", "Remote - US")
    assert await classify_stored_jobs(session) == 1

    assert await classify_stored_jobs(session) == 0


async def test_the_raw_location_is_never_overwritten(session: AsyncSession) -> None:
    """Story 21. The derived country sits beside the text, never replaces it.

    Same principle as resume dates: a derived value that guessed wrong should be visibly wrong
    rather than quietly authoritative.
    """
    original = "CA-Toronto, CA-Montreal "
    await _add(session, 1, "Backend Engineer", original)

    await classify_stored_jobs(session)

    job = (await session.execute(select(Job))).scalar_one()
    assert job.location_raw == original
    assert job.country == "CA"


# --- the filters ----------------------------------------------------------------------


async def test_seniority_filter_excludes_rather_than_reorders(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _add(session, 1, "Senior Software Engineer")
    await _add(session, 2, "Software Engineer Intern")
    await classify_stored_jobs(session)

    assert await _titles(client, "seniority=entry") == ["Software Engineer Intern"]


async def test_seniority_accepts_several_values(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The filter a graduating student actually wants.

    Explicit entry-level postings are rare — 14 of 2,586 in the real index — so a feed showing
    only those is nearly empty. Excluding what is definitely too senior while keeping the
    unmarked majority is the useful query, and it needs both values at once.
    """
    await _add(session, 1, "Senior Software Engineer")
    await _add(session, 2, "Software Engineer Intern")
    await _add(session, 3, "Software Engineer")
    await classify_stored_jobs(session)

    titles = await _titles(client, "seniority=entry,unknown")

    assert set(titles) == {"Software Engineer Intern", "Software Engineer"}


async def test_role_family_filter(client: AsyncClient, session: AsyncSession) -> None:
    await _add(session, 1, "Software Engineer")
    await _add(session, 2, "Account Executive")
    await _add(session, 3, "Data Scientist")
    await classify_stored_jobs(session)

    assert await _titles(client, "role_family=software_engineering") == ["Software Engineer"]
    assert set(await _titles(client, "role_family=software_engineering,data_ml")) == {
        "Software Engineer",
        "Data Scientist",
    }


async def test_country_filter_is_hard(client: AsyncClient, session: AsyncSession) -> None:
    """A job in a country the student cannot work in is not a lesser match.

    Spike 001 found company boards skew to Bengaluru, Mexico City and Singapore, which is why
    this is an exclusion and not a ranking signal.
    """
    await _add(session, 1, "Software Engineer", "Toronto, ON")
    await _add(session, 2, "Software Engineer", "Bengaluru, India")
    await _add(session, 3, "Software Engineer", "New York, NY")
    await classify_stored_jobs(session)

    assert await _titles(client, "country=CA") == ["Software Engineer"]
    assert len(await _titles(client, "country=US,CA")) == 2


async def test_remote_filter(client: AsyncClient, session: AsyncSession) -> None:
    await _add(session, 1, "Backend Engineer", "US-Remote, Chicago")
    await _add(session, 2, "Backend Engineer", "Chicago, IL")
    await classify_stored_jobs(session)

    assert len(await _titles(client, "remote=true")) == 1


async def test_keyword_search_covers_title_and_description(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _add(session, 1, "Backend Engineer")
    await _add(session, 2, "Frontend Engineer")

    assert await _titles(client, "q=backend") == ["Backend Engineer"]
    assert len(await _titles(client, "q=engineer")) == 2


async def test_filters_combine(client: AsyncClient, session: AsyncSession) -> None:
    await _add(session, 1, "Software Engineer Intern", "Toronto, ON")
    await _add(session, 2, "Software Engineer Intern", "Bengaluru, India")
    await _add(session, 3, "Senior Software Engineer", "Toronto, ON")
    await _add(session, 4, "Account Executive", "Toronto, ON")
    await classify_stored_jobs(session)

    titles = await _titles(
        client, "seniority=entry&country=CA&role_family=software_engineering"
    )

    assert titles == ["Software Engineer Intern"]


async def test_the_response_states_which_filters_are_active(
    client: AsyncClient, session: AsyncSession
) -> None:
    """So an empty result can name the filter responsible rather than saying nothing matched."""
    await _add(session, 1, "Software Engineer", "Toronto, ON")
    await classify_stored_jobs(session)

    payload = (await client.get("/api/v1/jobs?country=US&seniority=entry")).json()

    assert payload["total"] == 0
    assert payload["applied_filters"]["country"] == ["US"]
    assert payload["applied_filters"]["seniority"] == ["entry"]


async def test_an_unknown_filter_value_is_rejected_not_ignored(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Silently ignoring it would show a student a feed they did not ask for.

    They would then reasonably conclude the filter does nothing.
    """
    await _add(session, 1, "Software Engineer")

    response = await client.get("/api/v1/jobs?role_family=wizardry")

    assert response.status_code == 422


async def test_a_closed_job_stays_out_however_the_filters_are_set(
    client: AsyncClient, session: AsyncSession
) -> None:
    job = await _add(session, 1, "Software Engineer", "Toronto, ON")
    await classify_stored_jobs(session)
    job.closed_at = datetime.now(UTC)
    await session.commit()

    assert await _titles(client, "country=CA") == []
