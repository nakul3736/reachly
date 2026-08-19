"""Fetching a board and folding its postings into the shared index.

The only module here that both talks to the database and knows what order things happen in.
Adapters stay pure, and this decides what a fetch means.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.http import get_http_client
from app.adapters.job_sources import ashby, greenhouse, lever, muse
from app.domain.job_posting import RawPosting
from app.domain.location import extract_location
from app.domain.role_family import classify_role_family, classify_seniority
from app.models.board_token import BoardToken
from app.models.job import Job

logger = logging.getLogger(__name__)

_BOARD_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
}

# Typed loosely on purpose: Lever returns a bare array where the other two return an object, so
# there is no single payload type to promise. The adapters each know their own shape, and that
# knowledge belongs in them rather than being flattened into a lowest common denominator here.
_PARSERS: dict[str, Callable[..., list[RawPosting]]] = {
    "greenhouse": greenhouse.parse_greenhouse_board,
    "lever": lever.parse_lever_board,
    "ashby": ashby.parse_ashby_board,
}

_MUSE_URL = "https://www.themuse.com/api/public/jobs?page={page}&level=Entry%20Level"


@dataclass
class IngestResult:
    """What one board fetch did.

    `succeeded` is separate from the counts because zero created and zero updated is a
    perfectly good outcome for a board with nothing new, and indistinguishable from a
    failure if only the numbers are reported. Ticket 05 turns that distinction into a rule:
    absence from a *successful* fetch is what closes a job.
    """

    succeeded: bool
    created: int = 0
    updated: int = 0
    skipped: int = 0
    seen_source_ids: frozenset[str] = frozenset()
    error: str | None = None


async def ingest_board(
    session: AsyncSession, board: BoardToken, *, client: httpx.AsyncClient
) -> IngestResult:
    """Fetch one board and upsert what it returned.

    Never raises for a provider problem. One dead company must not be able to take down a
    refresh that has thirty other boards to visit, so failure is a returned value and the
    board's own failure counters carry the news.
    """
    board.last_fetched_at = datetime.now(UTC)

    url = _BOARD_URLS[board.provider].format(token=board.token)

    try:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        message = f"{type(exc).__name__}: {exc}"[:500]
        board.consecutive_failures += 1
        board.last_error = message
        await session.commit()
        logger.warning("board fetch failed: %s/%s — %s", board.provider, board.token, message)
        return IngestResult(succeeded=False, error=message)

    postings = _PARSERS[board.provider](payload, company_name=board.company_name)

    result = await _upsert(session, postings, source=board.provider)

    board.last_succeeded_at = datetime.now(UTC)
    board.consecutive_failures = 0
    board.last_error = None
    await session.commit()

    return result


@dataclass
class RefreshSummary:
    """What a whole refresh did, per source.

    Reported rather than logged and forgotten, because story 28 asks for a silently broken
    adapter to be visible. A source that fetched successfully and created nothing for a week
    is the failure that hides best.
    """

    boards_attempted: int = 0
    boards_succeeded: int = 0
    boards_failed: int = 0
    # Registered, but Reachly has no adapter for that provider yet. Counted apart from
    # failures on purpose: a board nobody has tried is not a board that is broken, and
    # folding the two together would make the interface cry wolf.
    boards_skipped: int = 0
    # The Muse, tracked apart from boards because it is not one. It covers every company from a
    # single endpoint, so it has no token, no registry row, and its absence proves nothing.
    aggregator_attempted: bool = False
    aggregator_succeeded: bool = False
    created: int = 0
    updated: int = 0


async def refresh_all_boards(
    session: AsyncSession, *, client: httpx.AsyncClient | None = None
) -> RefreshSummary:
    """Fetch every active board, one at a time, isolating failures.

    Sequential on purpose. Concurrency would finish sooner, but the free host has one small
    container and a burst of parallel requests to the same provider is exactly the shape that
    earns a rate limit. The refresh has all day.
    """
    boards = (
        (
            await session.execute(
                select(BoardToken)
                .where(BoardToken.active.is_(True))
                .order_by(BoardToken.consecutive_failures, BoardToken.id)
            )
        )
        .scalars()
        .all()
    )

    summary = RefreshSummary()
    owns_client = client is None
    active_client = client or get_http_client()

    try:
        for board in boards:
            # Checked here rather than inside ingest_board so an unsupported provider never
            # counts as an attempt. The registry is seeded with every provider up front,
            # while adapters arrive one ticket at a time.
            if board.provider not in _PARSERS:
                summary.boards_skipped += 1
                logger.info("no adapter for provider %s, skipping", board.provider)
                continue

            summary.boards_attempted += 1
            result = await ingest_board(session, board, client=active_client)
            if result.succeeded:
                summary.boards_succeeded += 1
                summary.created += result.created
                summary.updated += result.updated
            else:
                summary.boards_failed += 1
        # The Muse last, and counted separately, because it is one endpoint for every company
        # rather than a board per company. Folding it into the board counters would make
        # "boards attempted" a number that does not correspond to any company, and story 28
        # depends on those counts meaning something precise.
        summary.aggregator_attempted = True
        muse_result = await ingest_muse(session, client=active_client)
        summary.aggregator_succeeded = muse_result.succeeded
        summary.created += muse_result.created
        summary.updated += muse_result.updated
    finally:
        if owns_client:
            await active_client.aclose()

    logger.info(
        "refresh complete: %d/%d boards ok, %d skipped, %d created, %d updated",
        summary.boards_succeeded,
        summary.boards_attempted,
        summary.boards_skipped,
        summary.created,
        summary.updated,
    )
    return summary


async def ingest_muse(
    session: AsyncSession, *, client: httpx.AsyncClient, max_pages: int = muse.MAX_PAGES
) -> IngestResult:
    """Read the first few pages of The Muse's entry-level feed.

    Not a board, and deliberately not in the board registry: The Muse is one endpoint covering
    every company, so a per-company token would be a fiction. It is also an aggregator, which
    changes two rules downstream — its postings are stored unverified, and their absence from a
    later read proves nothing, so they expire on a timer instead of being swept.

    Bounded at a handful of pages. The API reports 4,493 of them, roughly ninety thousand
    postings, which no free host is ingesting in a request window. Pages come newest first, so a
    bounded read takes the freshest slice rather than an arbitrary one.

    A page that fails ends the walk instead of failing the whole ingest. Whatever earlier pages
    returned is real and worth keeping, and the next run will start again from page one.
    """
    total = IngestResult(succeeded=True)
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        try:
            response = await client.get(_MUSE_URL.format(page=page), timeout=30.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("muse page %d failed, stopping the walk: %s", page, exc)
            break

        postings = muse.parse_muse_page(payload)
        if not postings:
            break

        result = await _upsert(session, postings, source=muse.SOURCE)
        total.created += result.created
        total.updated += result.updated
        seen |= result.seen_source_ids

        await session.commit()

    total.seen_source_ids = frozenset(seen)
    logger.info("muse: %d created, %d updated", total.created, total.updated)
    return total


async def _upsert(
    session: AsyncSession, postings: list[RawPosting], *, source: str
) -> IngestResult:
    """Create what is new, refresh what is not.

    `first_seen_at` is never touched on an existing row. It is what story 22 needs in order
    to distinguish a job the student has already scrolled past from one that appeared today,
    and overwriting it would make everything permanently look new.
    """
    if not postings:
        return IngestResult(succeeded=True, seen_source_ids=frozenset())

    ids = [p.source_job_id for p in postings]
    existing_rows = (
        await session.execute(
            select(Job).where(Job.source == source, Job.source_job_id.in_(ids))
        )
    ).scalars()
    existing = {row.source_job_id: row for row in existing_rows}

    created = 0
    updated = 0
    now = datetime.now(UTC)

    for posting in postings:
        row = existing.get(posting.source_job_id)
        location = extract_location(posting.location_raw)
        role_family = classify_role_family(posting.title)
        seniority = str(classify_seniority(posting.title))

        # A provider's own claim is consulted only where our rules found nothing.
        #
        # The Muse marking "Security Officer" as entry level is a fact no title rule can derive,
        # and discarding it would throw away the one thing that source is better at. But the
        # hint never overrides a rule that did fire, because an aggregator would then be able to
        # relabel a senior role into a graduate's feed — and the senior rules are the ones
        # protecting the student's time.
        if seniority == "unknown" and posting.seniority_hint:
            seniority = posting.seniority_hint

        is_remote = (
            posting.is_remote_hint
            if posting.is_remote_hint is not None
            else location.is_remote
        )
        if row is None:
            session.add(
                Job(
                    source=posting.source,
                    source_job_id=posting.source_job_id,
                    company_name=posting.company_name,
                    title=posting.title,
                    location_raw=posting.location_raw,
                    country=location.country,
                    is_remote=is_remote,
                    role_family=role_family,
                    seniority=seniority,
                    description=posting.description,
                    apply_url=posting.apply_url,
                    posted_at=posting.posted_at,
                    is_verified=posting.is_verified,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            created += 1
            continue

        # A posting can be edited in place by the employer, so the mutable fields are
        # refreshed. Title and description changes are the ones that matter: a stale
        # description is what a student would tailor against.
        row.title = posting.title
        row.description = posting.description
        row.location_raw = posting.location_raw
        row.apply_url = posting.apply_url
        row.last_seen_at = now

        # Reclassified with the title, because an employer editing "Engineer" to "Senior
        # Engineer" changes who the posting is for. Leaving the old classification would keep
        # it in a graduate's feed after it stopped belonging there.
        row.country = location.country
        row.is_remote = is_remote
        row.role_family = role_family
        row.seniority = seniority

        # A job that reappears after being closed is reopened rather than duplicated.
        # Roles genuinely get reposted, and a second row would defeat dedup before it runs.
        row.closed_at = None

        updated += 1

    await session.flush()

    return IngestResult(
        succeeded=True,
        created=created,
        updated=updated,
        seen_source_ids=frozenset(ids),
    )
