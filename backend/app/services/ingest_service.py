"""Fetching a board and folding its postings into the shared index.

The only module here that both talks to the database and knows what order things happen in.
Adapters stay pure, and this decides what a fetch means.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, true
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

# How long a whole run may take. The free host will terminate a request that outlives its limit,
# and a terminated run reports nothing at all — no counts, no errors, no way to tell it from a
# run
# that found nothing. Stopping early with a truthful summary is strictly better.
DEFAULT_MAX_SECONDS = 240.0

# Backoff. A board that has failed repeatedly is asked less often, because eighteen boards share
# one finite window and a company that deleted its board should not keep its full share of it.
#
# A delay rather than deactivation, deliberately: a board can come back, only an attempt can
# discover that, and nothing in this system would ever reactivate a board it had given up on.
_BACKOFF_BASE_HOURS = 2.0
_BACKOFF_MAX_HOURS = 72.0
# Below this, failures are treated as noise. Providers return the occasional 500 and recover in
# a
# minute, and backing off after one of those would make the index worse for no reason.
_BACKOFF_AFTER_FAILURES = 3


def should_attempt(board: BoardToken) -> bool:
    """Whether this board has waited long enough after repeated failures.

    Exponential in the failure count and capped, so a permanently dead board settles at one
    attempt every three days rather than doubling its way into never being tried again.
    """
    if board.consecutive_failures < _BACKOFF_AFTER_FAILURES:
        return True
    if board.last_fetched_at is None:
        return True

    over = board.consecutive_failures - _BACKOFF_AFTER_FAILURES
    delay_hours = min(_BACKOFF_BASE_HOURS * (2**over), _BACKOFF_MAX_HOURS)

    last = board.last_fetched_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return datetime.now(UTC) - last >= timedelta(hours=delay_hours)


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
    # Transitioned to closed by this fetch. Counts the transition rather than the total number
    # of closed jobs, so a sweep that closes nothing new reports zero instead of a growing
    # number that looks like an escalating problem.
    closed: int = 0
    reopened: int = 0
    # A 200 carrying an empty list where this board previously had postings. Not treated as
    # closure and not discarded either: it is the shape a provider returns for a deleted board,
    # a rotated token, and an adapter that stopped matching the payload.
    suspicious: bool = False
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

    result = await _upsert(session, postings, source=board.provider, board=board)

    # The sweep runs only here — on the success path, after a fetch that returned something.
    # Both conditions are load-bearing, and each has its own test, because getting either wrong
    # empties the feed rather than merely leaving a dead job in it.
    if postings:
        result.closed = await _sweep_closures(session, board, result.seen_source_ids)
    else:
        # An empty list is not evidence that a company filled every role at once. It is far more
        # likely a deleted board, a rotated token, or an adapter that stopped matching the
        # payload — and a board with genuinely nothing open is normal and must not be flagged
        # forever, so previously having had postings is what makes this worth reporting.
        result.suspicious = await _has_open_jobs(session, board)
        if result.suspicious:
            logger.warning(
                "board %s/%s returned an empty list but has open jobs — not sweeping",
                board.provider,
                board.token,
            )

    board.last_succeeded_at = datetime.now(UTC)
    board.consecutive_failures = 0
    board.last_error = None
    await session.commit()

    return result


async def _has_open_jobs(session: AsyncSession, board: BoardToken) -> bool:
    found = (
        await session.execute(
            select(Job.id)
            .where(Job.board_token_id == board.id, Job.closed_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    return found is not None


async def _sweep_closures(
    session: AsyncSession, board: BoardToken, seen: frozenset[str]
) -> int:
    """Close this board's open jobs that the board no longer lists.

    Scoped by `board_token_id` rather than by source or company name. By source, Figma's refresh
    would close Linear's entire listing — both are Greenhouse, and neither appears in the
    other's response. By company name, a firm running a second board for a region would have
    each board close the other.

    `closed_at` is only written where it is null, so it records when absence was **first**
    observed. Overwriting it on every later sweep would make a role closed three weeks ago show
    as closed today, forever.
    """
    stale = (
        (
            await session.execute(
                select(Job).where(
                    Job.board_token_id == board.id,
                    Job.closed_at.is_(None),
                    Job.source_job_id.notin_(seen) if seen else true(),
                )
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    for job in stale:
        job.closed_at = now

    if stale:
        logger.info(
            "closed %d posting(s) no longer listed on %s/%s",
            len(stale),
            board.provider,
            board.token,
        )
    return len(stale)


async def expire_stale_aggregator_rows(
    session: AsyncSession, *, max_age_days: int = 14
) -> int:
    """Close unverified postings not seen for a while.

    The Muse is read a bounded number of pages deep and does not enumerate a complete set, so a
    posting missing from today's read may simply have moved to page thirteen. Absence therefore
    proves nothing about an aggregator row and cannot be allowed to close one — but leaving them
    forever would fill the feed with roles that quietly ended months ago.

    A timer is the honest compromise: it makes no claim about a specific posting, only that a
    copy of unknown age that has not been re-seen in two weeks is no longer worth a student's
    evening. Verified board rows are deliberately untouched by age. A company posting that has
    been open for six months is still open, and its board says so every day.
    """
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

    stale = (
        (
            await session.execute(
                select(Job).where(
                    Job.is_verified.is_(False),
                    Job.closed_at.is_(None),
                    Job.last_seen_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    for job in stale:
        job.closed_at = now

    await session.commit()
    if stale:
        logger.info(
            "expired %d aggregator posting(s) older than %d days",
            len(stale),
            max_age_days,
        )
    return len(stale)


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
    # Deferred by backoff. Counted apart from both failures and skips: this board is not broken
    # and does have an adapter, it simply failed often enough that asking again today is not
    # worth
    # the window. Conflating it with a failure would make the interface report a problem that
    # the
    # run deliberately avoided.
    boards_backed_off: int = 0
    # The Muse, tracked apart from boards because it is not one. It covers every company from a
    # single endpoint, so it has no token, no registry row, and its absence proves nothing.
    aggregator_attempted: bool = False
    aggregator_succeeded: bool = False
    created: int = 0
    updated: int = 0
    reopened: int = 0
    closed: int = 0
    # Broken out per source so a rule or adapter change that starts closing everything is
    # visible in the run that does it, rather than a week later when the feed is empty. A
    # single total would hide one source closing all of its postings behind four that did not.
    closed_by_source: dict[str, int] = field(default_factory=dict)
    aggregator_expired: int = 0
    # Boards that returned a 200 with nothing in it while holding open jobs. Named rather than
    # counted, because the useful question is which board to go and look at.
    suspicious_boards: list[str] = field(default_factory=list)
    # True when the run stopped early to stay inside its window. Reported rather than hidden: a
    # run that keeps hitting its deadline is a run that needs a longer window or fewer boards,
    # and
    # that is invisible if a truncated run looks identical to a complete one.
    deadline_reached: bool = False
    elapsed_seconds: float = 0.0


async def refresh_all_boards(
    session: AsyncSession,
    *,
    client: httpx.AsyncClient | None = None,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> RefreshSummary:
    """Fetch every active board, one at a time, isolating failures.

    Sequential on purpose. Concurrency would finish sooner, but the free host has one small
    container and a burst of parallel requests to the same provider is exactly the shape that
    earns a rate limit. The refresh has all day.

    Bounded by `max_seconds`. Boards not reached are still active and are fetched first next
    time,
    because the ordering below puts the least recently fetched at the front — so a run that is
    repeatedly cut short still covers the whole registry over a few triggers rather than
    favouring
    whichever boards happen to sort first.
    """
    boards = (
        (
            await session.execute(
                select(BoardToken)
                .where(BoardToken.active.is_(True))
                .order_by(
                    # Never-fetched boards first, then the most neglected. This is what makes a
                    # truncated run fair: the boards a short run misses are the ones the next
                    # run
                    # starts with.
                    BoardToken.last_fetched_at.is_not(None),
                    BoardToken.last_fetched_at,
                    BoardToken.id,
                )
            )
        )
        .scalars()
        .all()
    )

    summary = RefreshSummary()
    owns_client = client is None
    active_client = client or get_http_client()
    started = time.monotonic()

    try:
        for board in boards:
            if time.monotonic() - started >= max_seconds:
                summary.deadline_reached = True
                logger.info(
                    "refresh deadline reached after %d board(s)", summary.boards_attempted
                )
                break

            # Checked here rather than inside ingest_board so an unsupported provider never
            # counts as an attempt. The registry is seeded with every provider up front,
            # while adapters arrive one ticket at a time.
            if board.provider not in _PARSERS:
                summary.boards_skipped += 1
                logger.info("no adapter for provider %s, skipping", board.provider)
                continue

            if not should_attempt(board):
                summary.boards_backed_off += 1
                continue

            summary.boards_attempted += 1
            result = await ingest_board(session, board, client=active_client)
            if result.succeeded:
                summary.boards_succeeded += 1
                summary.created += result.created
                summary.updated += result.updated
                summary.reopened += result.reopened
                summary.closed += result.closed
                if result.closed:
                    summary.closed_by_source[board.provider] = (
                        summary.closed_by_source.get(board.provider, 0) + result.closed
                    )
                if result.suspicious:
                    summary.suspicious_boards.append(f"{board.provider}/{board.token}")
            else:
                summary.boards_failed += 1
        # The Muse last, and counted separately, because it is one endpoint for every company
        # rather than a board per company. Folding it into the board counters would make
        # "boards attempted" a number that does not correspond to any company, and story 28
        # depends on those counts meaning something precise.
        if time.monotonic() - started < max_seconds:
            summary.aggregator_attempted = True
            muse_result = await ingest_muse(session, client=active_client)
            summary.aggregator_succeeded = muse_result.succeeded
            summary.created += muse_result.created
            summary.updated += muse_result.updated
            summary.reopened += muse_result.reopened
        else:
            summary.deadline_reached = True

        # Aggregator rows expire on age instead of absence, so this runs once per refresh rather
        # than per source. Counted apart from swept closures because it is a weaker claim: a
        # board says a job is gone, a timer only says nobody has confirmed it lately.
        expired = await expire_stale_aggregator_rows(session)
        summary.aggregator_expired = expired
        summary.closed += expired
        if expired:
            summary.closed_by_source[muse.SOURCE] = (
                summary.closed_by_source.get(muse.SOURCE, 0) + expired
            )
    finally:
        if owns_client:
            await active_client.aclose()

    summary.elapsed_seconds = round(time.monotonic() - started, 2)

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
    session: AsyncSession,
    postings: list[RawPosting],
    *,
    source: str,
    board: BoardToken | None = None,
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
    reopened = 0
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
                    board_token_id=board.id if board is not None else None,
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
        # Counted, because a board that reopens the same postings every day is a board whose
        # ids are unstable, and that shows up here before it shows up as a duplicated feed.
        if row.closed_at is not None:
            row.closed_at = None
            reopened += 1

        # Backfilled for rows created before the board link existed, so the first sweep after
        # this ships is correctly scoped rather than silently skipping every older posting.
        if board is not None and row.board_token_id is None:
            row.board_token_id = board.id

        updated += 1

    await session.flush()

    return IngestResult(
        succeeded=True,
        created=created,
        updated=updated,
        reopened=reopened,
        seen_source_ids=frozenset(ids),
    )
