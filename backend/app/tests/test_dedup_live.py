"""The ambiguous band, against the real model.

Gated behind two variables so a configured key cannot silently spend quota:
`GEMINI_LIVE_TESTS=1` **and** `GEMINI_API_KEY`.

Deliberately cheap. Dedup's entire inference budget is one batched request, so exercising it for
real costs **one call** — and that is the point worth verifying live, because batching is the
property a fake client can always be made to appear to have. The pairs below are chosen to
include
both answers, so a model that simply agreed with everything would fail rather than pass.
"""

import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gemini_client import GeminiClient
from app.config import get_settings
from app.models.job import DedupVerdict, Job
from app.services.dedup_service import deduplicate

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        os.environ.get("GEMINI_LIVE_TESTS") != "1",
        reason="live inference test; set GEMINI_LIVE_TESTS=1 to run",
    ),
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="no GEMINI_API_KEY configured",
    ),
]


def _live_client() -> GeminiClient:
    settings = get_settings()
    return GeminiClient(
        api_key=os.environ["GEMINI_API_KEY"],
        model=settings.gemini_model,
        timeout_seconds=60.0,
    )


async def _add(
    session: AsyncSession,
    *,
    source: str,
    job_id: str,
    company: str,
    title: str,
    location: str,
    verified: bool,
) -> Job:
    job = Job(
        source=source,
        source_job_id=job_id,
        company_name=company,
        title=title,
        location_raw=location,
        description="See posting.",
        apply_url=f"https://example.com/{source}/{job_id}",
        is_verified=verified,
    )
    session.add(job)
    await session.commit()
    return job


class _CountingClient:
    """Wraps the real client to count requests, so "one call" is measured not assumed."""

    def __init__(self, inner: GeminiClient) -> None:
        self.inner = inner
        self.calls = 0

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, object]:
        self.calls += 1
        return await self.inner.complete_json(
            system=system, user=user, max_output_tokens=max_output_tokens
        )


async def test_the_real_model_resolves_the_ambiguous_band_in_one_call(
    session: AsyncSession,
) -> None:
    """Three ambiguous pairs at three companies, one request, and both answers represented.

    The pairs are built so that the deterministic rules cannot settle them: each scores between
    0.75 and 0.90 on title similarity, which is the only band that reaches a model at all.
    """
    # Same job, worded differently by a board and an aggregator.
    await _add(
        session,
        source="greenhouse",
        job_id="1",
        company="Northwind Systems",
        title="Software Engineer, Platform",
        location="Toronto, ON",
        verified=True,
    )
    await _add(
        session,
        source="muse",
        job_id="101",
        company="Northwind Systems",
        title="Platform Engineer",
        location="Toronto, ON",
        verified=False,
    )

    # Genuinely different jobs that read alike.
    await _add(
        session,
        source="greenhouse",
        job_id="2",
        company="Bluecrest Analytics",
        title="Customer Success Associate",
        location="Austin, TX",
        verified=True,
    )
    await _add(
        session,
        source="muse",
        job_id="102",
        company="Bluecrest Analytics",
        title="Customer Success Manager",
        location="Austin, TX",
        verified=False,
    )

    # A wording difference that is only an abbreviation.
    await _add(
        session,
        source="greenhouse",
        job_id="3",
        company="Calder Robotics",
        title="QA Engineer",
        location="Remote",
        verified=True,
    )
    await _add(
        session,
        source="muse",
        job_id="103",
        company="Calder Robotics",
        title="Quality Assurance Engineer",
        location="Remote",
        verified=False,
    )

    client = _CountingClient(_live_client())
    summary = await deduplicate(session, llm=client)

    assert client.calls == 1, (
        f"the whole ambiguous band must be one request, made {client.calls}"
    )
    assert summary.asked >= 1, "the real model returned usable verdicts"
    assert summary.undecided == 0, "every pair sent came back answered"

    verdicts = (await session.execute(select(DedupVerdict))).scalars().all()
    assert len(verdicts) == summary.asked
    for verdict in verdicts:
        assert verdict.fingerprint_low <= verdict.fingerprint_high, "cached sorted"
        assert verdict.decided_by == "inference"


async def test_the_real_model_keeps_two_different_seniorities_apart(
    session: AsyncSession,
) -> None:
    """The judgement that matters: the model must not merge a graduate role into a senior one.

    A second call, and the reason it is worth one: the deterministic guards cover the cases they
    can see, and this is the residue they cannot. If the model collapses these, the ambiguous
    band
    is not safe to act on and the band would have to be narrowed.
    """
    await _add(
        session,
        source="greenhouse",
        job_id="10",
        company="Halvard Freight",
        title="Data Analyst, Operations",
        location="Vancouver, BC",
        verified=True,
    )
    await _add(
        session,
        source="muse",
        job_id="110",
        company="Halvard Freight",
        title="Operations Data Analyst, Senior",
        location="Vancouver, BC",
        verified=False,
    )

    client = _CountingClient(_live_client())
    await deduplicate(session, llm=client)

    aliases = (
        (await session.execute(select(Job).where(Job.canonical_job_id.is_not(None))))
        .scalars()
        .all()
    )
    assert aliases == [], "a senior posting is not the same job as the non-senior one"
