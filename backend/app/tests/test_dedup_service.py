"""Collapsing duplicate postings into one feed row.

Adding The Muse is what made this necessary: it carries almost all the entry-level roles, and it
carries them by syndicating the board postings Reachly already has. Without dedup the source
that
makes the product useful also makes the feed worse.

The rules are ordered by cost. Exact fingerprint match is free, fuzzy comparison is cheap,
inference is the only thing that costs money and it is confined to a narrow band and batched
into
one call. Everything outside that band is decided without asking anybody.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.llm_client import LLMUnavailable
from app.models.job import DedupVerdict, Job
from app.services.dedup_service import deduplicate

pytestmark = pytest.mark.anyio


class _RecordingLLM:
    """Counts calls, so "batched" can be asserted rather than hoped for.

    Answers every numbered pair it is sent, which is what a working model does. `verdicts` keys
    the answer by the pair number when a specific outcome matters; anything unlisted gets
    `default`.
    """

    def __init__(
        self, verdicts: dict[str, bool] | None = None, default: bool = True
    ) -> None:
        self.calls = 0
        self.last_user = ""
        self.verdicts = verdicts or {}
        self.default = default

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, object]:
        self.calls += 1
        self.last_user = user

        numbers = re.findall(r"^(\d+)\.", user, re.MULTILINE)
        pairs = [
            {"pair": number, "same_job": self.verdicts.get(number, self.default)}
            for number in numbers
        ]
        return {"pairs": pairs}


class _BrokenLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, object]:
        self.calls += 1
        raise LLMUnavailable("quota exhausted")


async def _job(
    session: AsyncSession,
    *,
    source: str,
    job_id: str,
    company: str,
    title: str,
    location: str | None = "Toronto, ON",
    verified: bool = True,
    first_seen: datetime | None = None,
) -> Job:
    job = Job(
        source=source,
        source_job_id=job_id,
        company_name=company,
        title=title,
        location_raw=location,
        description="Build things.",
        apply_url=f"https://example.com/{source}/{job_id}",
        is_verified=verified,
        first_seen_at=first_seen or datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(job)
    await session.commit()
    return job


async def _reload(session: AsyncSession, job: Job) -> Job:
    await session.refresh(job)
    return job


# --- exact, and free -------------------------------------------------------------------


async def test_the_same_job_on_a_board_and_an_aggregator_collapses(
    session: AsyncSession,
) -> None:
    board = await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Shopify Inc.",
        title="Software Engineer (REQ-1029)",
        location="Toronto, ON, Canada",
    )
    aggregator = await _job(
        session,
        source="muse",
        job_id="9",
        company="Shopify",
        title="Software Engineer",
        location="Toronto, ON",
        verified=False,
    )

    llm = _RecordingLLM()
    summary = await deduplicate(session, llm=llm)

    assert summary.collapsed == 1
    assert summary.decided_by["exact"] == 1
    assert llm.calls == 0, "an exact match costs nothing"

    assert (await _reload(session, board)).canonical_job_id is None
    assert (await _reload(session, aggregator)).canonical_job_id == board.id


async def test_the_board_record_wins_regardless_of_which_was_seen_first(
    session: AsyncSession,
) -> None:
    """The board is the company's own statement; the aggregator is a copy of unknown age.

    Insertion order must not decide this. The aggregator is seeded first here precisely because
    an implementation that keeps whichever row it met first would pass a test written the other
    way round.
    """
    aggregator = await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Product Designer",
        verified=False,
        first_seen=datetime.now(UTC) - timedelta(days=5),
    )
    board = await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Figma",
        title="Product Designer",
        verified=True,
    )

    await deduplicate(session, llm=_RecordingLLM())

    assert (await _reload(session, board)).canonical_job_id is None
    assert (await _reload(session, aggregator)).canonical_job_id == board.id


async def test_between_two_boards_the_earlier_sighting_wins(
    session: AsyncSession,
) -> None:
    """Both are verified, so seniority of evidence is the only tiebreak left.

    Keeping the older row means the student's `first_seen_at` and any tracking against it
    survive
    rather than being reset by a re-post.
    """
    older = await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Linear",
        title="Backend Engineer",
        first_seen=datetime.now(UTC) - timedelta(days=10),
    )
    newer = await _job(
        session,
        source="ashby",
        job_id="2",
        company="Linear",
        title="Backend Engineer",
        first_seen=datetime.now(UTC),
    )

    await deduplicate(session, llm=_RecordingLLM())

    assert (await _reload(session, older)).canonical_job_id is None
    assert (await _reload(session, newer)).canonical_job_id == older.id


# --- scoping ---------------------------------------------------------------------------


async def test_similar_titles_at_different_companies_never_collapse(
    session: AsyncSession,
) -> None:
    """Every firm has a Software Engineer, so cross-company title similarity means nothing.

    This is the single most destructive thing dedup could do: without company scoping, one
    generic title would collapse hundreds of unrelated openings into one row.
    """
    figma = await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Software Engineer"
    )
    linear = await _job(
        session, source="greenhouse", job_id="2", company="Linear", title="Software Engineer"
    )
    stripe = await _job(
        session, source="ashby", job_id="3", company="Stripe", title="Software Engineer"
    )

    llm = _RecordingLLM()
    summary = await deduplicate(session, llm=llm)

    assert summary.collapsed == 0
    assert llm.calls == 0, "not even worth asking about"
    for job in (figma, linear, stripe):
        assert (await _reload(session, job)).canonical_job_id is None


async def test_the_same_company_written_differently_is_still_one_company(
    session: AsyncSession,
) -> None:
    board = await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Wealthsimple Ltd.",
        title="Data Analyst",
    )
    aggregator = await _job(
        session,
        source="muse",
        job_id="9",
        company="Wealthsimple",
        title="Data Analyst",
        verified=False,
    )

    await deduplicate(session, llm=_RecordingLLM())

    assert (await _reload(session, aggregator)).canonical_job_id == board.id


async def test_the_same_role_in_two_countries_never_collapses(
    session: AsyncSession,
) -> None:
    """The bug real data exposed, at the level where it did damage.

    Stripe lists `Director, Sales Compensation` once for the US and again for Canada — identical
    company, identical title, two genuinely different jobs. Six of twelve sampled collapses on
    the
    live index were this, and for a product scoped to US and Canadian graduates it removed half
    of
    the affected postings from the feed.
    """
    us = await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Stripe",
        title="Credit Risk Strategy and Analytics",
        location="United States",
    )
    canada = await _job(
        session,
        source="greenhouse",
        job_id="2",
        company="Stripe",
        title="Credit Risk Strategy and Analytics",
        location="Canada",
    )
    us.country = "US"
    canada.country = "CA"
    await session.commit()

    summary = await deduplicate(session, llm=_RecordingLLM())

    assert summary.collapsed == 0
    assert (await _reload(session, us)).canonical_job_id is None
    assert (await _reload(session, canada)).canonical_job_id is None


async def test_the_same_role_in_two_cities_never_collapses(
    session: AsyncSession,
) -> None:
    """Same country, so the country guard cannot help — the location itself has to.

    A student in Vancouver should not have the Vancouver opening hidden behind the Toronto one.
    """
    toronto = await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Shopify",
        title="Software Engineer",
        location="Toronto, ON",
    )
    vancouver = await _job(
        session,
        source="greenhouse",
        job_id="2",
        company="Shopify",
        title="Software Engineer",
        location="Vancouver, BC",
    )

    summary = await deduplicate(session, llm=_RecordingLLM())

    assert summary.collapsed == 0
    assert (await _reload(session, vancouver)).canonical_job_id is None
    assert (await _reload(session, toronto)).canonical_job_id is None


async def test_the_same_role_described_with_more_detail_still_collapses(
    session: AsyncSession,
) -> None:
    """The guard must not be so strict that the aggregator can never match its source."""
    board = await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Shopify",
        title="Software Engineer",
        location="Toronto",
    )
    aggregator = await _job(
        session,
        source="muse",
        job_id="9",
        company="Shopify",
        title="Software Engineer",
        location="Toronto, Ontario, Canada",
        verified=False,
    )

    await deduplicate(session, llm=_RecordingLLM())

    assert (await _reload(session, aggregator)).canonical_job_id == board.id


# --- the bands -------------------------------------------------------------------------


async def test_a_close_but_inexact_title_collapses_without_inference(
    session: AsyncSession,
) -> None:
    """Above 0.90, reordered and lightly reworded titles are decided for free."""
    board = await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Figma",
        title="Software Engineer, New Grad",
    )
    aggregator = await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="New Grad Software Engineer",
        verified=False,
    )

    llm = _RecordingLLM()
    summary = await deduplicate(session, llm=llm)

    assert summary.collapsed == 1
    assert summary.decided_by["fuzzy"] == 1
    assert llm.calls == 0
    assert (await _reload(session, aggregator)).canonical_job_id == board.id


async def test_a_distant_title_at_the_same_company_stays_distinct_for_free(
    session: AsyncSession,
) -> None:
    """Below 0.75, no inference. A company has many different openings."""
    engineer = await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Software Engineer"
    )
    recruiter = await _job(
        session, source="greenhouse", job_id="2", company="Figma", title="Technical Recruiter"
    )

    llm = _RecordingLLM()
    summary = await deduplicate(session, llm=llm)

    assert summary.collapsed == 0
    assert llm.calls == 0
    assert (await _reload(session, recruiter)).canonical_job_id is None
    assert (await _reload(session, engineer)).canonical_job_id is None


async def test_two_levels_of_the_same_role_never_collapse(session: AsyncSession) -> None:
    """`Engineer II` and `Engineer III` are one character apart and different jobs.

    Raw token similarity puts these well above the collapse threshold. Getting this wrong hides
    a
    graduate-appropriate opening behind a senior one.
    """
    two = await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Software Engineer II"
    )
    three = await _job(
        session, source="greenhouse", job_id="2", company="Figma", title="Software Engineer III"
    )

    llm = _RecordingLLM()
    summary = await deduplicate(session, llm=llm)

    assert summary.collapsed == 0
    assert llm.calls == 0, "the level difference is decisive, not ambiguous"
    assert (await _reload(session, three)).canonical_job_id is None
    assert (await _reload(session, two)).canonical_job_id is None


async def test_a_seniority_difference_decides_without_paying_for_inference(
    session: AsyncSession,
) -> None:
    """`Data Analyst` and `Senior Data Analyst` score 0.77 — inside the ambiguous band.

    Ticket 04 already classified one as senior and the other as not, and that is a difference in
    who the job is for rather than in how the title is worded. Reusing the classification
    decides
    the pair for free and keeps it out of the only part of this feature that costs money.
    """
    junior = await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Data Analyst"
    )
    senior = await _job(
        session, source="greenhouse", job_id="2", company="Figma", title="Senior Data Analyst"
    )
    junior.seniority = "entry"
    junior.role_family = "data_ml"
    senior.seniority = "senior"
    senior.role_family = "data_ml"
    await session.commit()

    llm = _RecordingLLM()
    summary = await deduplicate(session, llm=llm)

    assert summary.collapsed == 0
    assert llm.calls == 0, "already known to be different jobs"
    assert (await _reload(session, senior)).canonical_job_id is None


async def test_different_role_families_never_collapse(session: AsyncSession) -> None:
    """A support role and an engineering role at one company are not one posting."""
    engineer = await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Support Engineer"
    )
    support = await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Support Specialist",
        verified=False,
    )
    engineer.role_family = "software_engineering"
    support.role_family = "support"
    await session.commit()

    llm = _RecordingLLM()
    summary = await deduplicate(session, llm=llm)

    assert summary.collapsed == 0
    assert llm.calls == 0


# --- the one inference call ------------------------------------------------------------


async def test_the_ambiguous_band_is_one_batched_call(session: AsyncSession) -> None:
    """Several ambiguous pairs, one request.

    A call per pair would multiply the only cost in this feature by the size of the index, which
    on a free tier means the feature stops working partway through a refresh.
    """
    await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Figma",
        title="Software Engineer, Platform",
    )
    await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Platform Engineer",
        verified=False,
    )
    await _job(
        session,
        source="greenhouse",
        job_id="2",
        company="Linear",
        title="Product Support Specialist",
    )
    await _job(
        session,
        source="muse",
        job_id="8",
        company="Linear",
        title="Support Specialist, Product",
        verified=False,
    )

    llm = _RecordingLLM()
    summary = await deduplicate(session, llm=llm)

    assert llm.calls <= 1, "batched across every ambiguous pair"
    assert summary.asked >= 1


async def test_an_inference_verdict_is_cached_on_the_sorted_pair(
    session: AsyncSession,
) -> None:
    """Stored sorted, so the same comparison cannot be paid for twice under two orderings."""
    await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Figma",
        title="Software Engineer, Platform",
    )
    await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Platform Engineer",
        verified=False,
    )

    first = _RecordingLLM()
    await deduplicate(session, llm=first)

    verdicts = (await session.execute(select(DedupVerdict))).scalars().all()
    assert len(verdicts) >= 1
    for verdict in verdicts:
        assert verdict.fingerprint_low <= verdict.fingerprint_high, "stored sorted"
        assert verdict.decided_by == "inference"

    second = _RecordingLLM()
    await deduplicate(session, llm=second)
    assert second.calls == 0, "already answered, and the answer cannot change"


async def test_inference_unavailable_leaves_both_rows_distinct(
    session: AsyncSession,
) -> None:
    """The cheap failure, chosen deliberately over the expensive one.

    An outage must not collapse rows on a guess. Two rows for one job wastes a little of the
    student's attention; one row hiding a real opening wastes the opportunity, and they cannot
    see that it happened. The feed keeps working either way.
    """
    board = await _job(
        session,
        source="greenhouse",
        job_id="1",
        company="Figma",
        title="Software Engineer, Platform",
    )
    aggregator = await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Platform Engineer",
        verified=False,
    )

    llm = _BrokenLLM()
    summary = await deduplicate(session, llm=llm)

    assert summary.undecided >= 1
    assert summary.collapsed == 0
    assert (await _reload(session, board)).canonical_job_id is None
    assert (await _reload(session, aggregator)).canonical_job_id is None
    assert (
        await session.execute(select(DedupVerdict))
    ).scalars().first() is None, "an outage is not a verdict, and must not be cached"


async def test_dedup_runs_without_inference_configured_at_all(
    session: AsyncSession,
) -> None:
    """Exact and fuzzy still work with no model available.

    The deterministic bands are the ones that matter, and they must not be gated behind having a
    provider — the deployed demo has no key at all.
    """
    board = await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Software Engineer"
    )
    aggregator = await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Software Engineer",
        verified=False,
    )

    summary = await deduplicate(session, llm=None)

    assert summary.collapsed == 1
    assert (await _reload(session, aggregator)).canonical_job_id == board.id


# --- interaction with closure ----------------------------------------------------------


async def test_a_canonical_that_closes_closes_the_job_even_if_the_alias_is_listed(
    session: AsyncSession,
) -> None:
    """The board is ground truth and the aggregator is the stale copy.

    The Muse continuing to list a filled role must not keep it in the feed. This is the whole
    reason `is_verified` exists.
    """
    from app.services.job_service import list_jobs

    board = await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Software Engineer"
    )
    await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Software Engineer",
        verified=False,
    )

    await deduplicate(session, llm=None)

    board.closed_at = datetime.now(UTC)
    await session.commit()

    page = await list_jobs(session)
    assert page.total == 0, "the alias must not resurrect a filled role"


async def test_an_alias_never_appears_as_its_own_feed_row(session: AsyncSession) -> None:
    from app.services.job_service import list_jobs

    board = await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Software Engineer"
    )
    await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Software Engineer",
        verified=False,
    )

    await deduplicate(session, llm=None)

    page = await list_jobs(session)
    assert page.total == 1
    assert [job.id for job in page.items] == [board.id]


# --- reruns ----------------------------------------------------------------------------


async def test_running_dedup_twice_changes_nothing_and_asks_nothing(
    session: AsyncSession,
) -> None:
    await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Software Engineer"
    )
    await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Software Engineer",
        verified=False,
    )

    first = await deduplicate(session, llm=_RecordingLLM())
    second = await deduplicate(session, llm=_RecordingLLM())

    assert first.collapsed == 1
    assert second.collapsed == 0, "already collapsed"

    aliases = (
        await session.execute(select(Job).where(Job.canonical_job_id.is_not(None)))
    ).scalars().all()
    assert len(aliases) == 1


async def test_dedup_works_over_stored_rows_without_refetching(
    session: AsyncSession,
) -> None:
    """So a threshold change can be reapplied without asking ten providers for the index again.

    Nothing here touches the network, which is the assertion: `deduplicate` takes a session and
    a
    model, and no transport at all.
    """
    await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Software Engineer"
    )
    await _job(
        session,
        source="muse",
        job_id="9",
        company="Figma",
        title="Software Engineer",
        verified=False,
    )

    summary = await deduplicate(session, llm=None)

    assert summary.compared >= 1
    assert summary.collapsed == 1


async def test_fingerprints_are_stored_so_they_are_computed_once(
    session: AsyncSession,
) -> None:
    job = await _job(
        session, source="greenhouse", job_id="1", company="Figma", title="Software Engineer"
    )

    await deduplicate(session, llm=None)

    stored = await _reload(session, job)
    assert stored.content_fingerprint is not None
    assert len(stored.content_fingerprint) == 32
