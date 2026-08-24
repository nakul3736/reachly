"""Externally triggered scheduled work.

ADR 0007: the scheduler lives outside the application. Render's free tier stops the
process when it goes idle, so an in-process timer stops firing and does so silently —
the feed would quietly go stale with nothing reporting a problem. A request from GitHub
Actions or cron-job.org both triggers the work and keeps the service awake.

Two deliberate choices:

* **A wrong or missing secret answers 404, not 401.** A 401 confirms the route exists,
  which tells a scanner there is something here worth attacking. To anyone without the
  secret this path is indistinguishable from a typo.
* **Handlers must be idempotent.** Two schedulers point at these endpoints and retries
  are expected, so running a task twice has to be harmless rather than merely unlikely.
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.llm_client import LLMClient, LLMError, get_llm_client
from app.config import get_settings
from app.db import get_session
from app.services.dedup_service import deduplicate
from app.services.ingest_service import DEFAULT_MAX_SECONDS, refresh_all_boards
from app.services.job_service import classify_stored_jobs
from app.services.skill_enrichment_service import EnrichmentSummary, enrich_job_skills

logger = logging.getLogger(__name__)

# The wall-clock budget for one refresh request.
#
# Set from measurement rather than taste: a healthy run of this endpoint takes about 100 seconds,
# and the scheduled run that failed took 440 before a proxy returned 502. 150 leaves headroom over
# the healthy case while staying far enough below the proxy's patience that a slow board or a
# rate-limited enrichment cannot push the request past it.
#
# Being cut short costs nothing durable. Boards are swept least-recently-fetched first, so a short
# run defers work to the next run rather than losing it, and the schedule runs twice a day.
_REQUEST_BUDGET_SECONDS = 150.0

# Enrichment is skipped when less than this remains. Twelve live batches with rate-limit backoff is
# the slowest thing in the request and the only phase whose absence degrades gracefully: without a
# fresh reading the vocabulary still produces a skill set, so every score still works.
_ENRICHMENT_RESERVE_SECONDS = 45.0

router = APIRouter(prefix="/internal/cron", tags=["internal"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _optional_llm() -> LLMClient | None:
    """The configured client, or None when there is no key and in demo mode.

    None rather than an exception: enrichment has a working fallback, so an unconfigured
    deployment should read descriptions with the vocabulary and say so, not fail a refresh.

    Demo mode deliberately gets None rather than the fixture client. A recorded fixture cannot
    honestly answer for thousands of postings it has never seen, and returning one anyway would
    label a vocabulary-only reading as a model reading — the exact deception non-negotiable 4
    forbids. Demo mode therefore reads with the vocabulary and the interface says so.
    """
    settings = get_settings()
    if settings.demo_mode:
        return None
    try:
        return get_llm_client()
    except LLMError:
        return None


async def verify_cron_secret(
    x_cron_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Reject anything without the shared secret, indistinguishably from a missing route.

    Also rejects when no secret is configured at all: an unset secret must fail closed,
    or a deployment that forgot to set one would expose the endpoints to everyone.
    """
    expected = get_settings().cron_secret
    if not expected or x_cron_secret != expected:
        raise _NOT_FOUND


CronAuth = Depends(verify_cron_secret)


@router.post("/keepalive", dependencies=[CronAuth])
async def keepalive() -> dict[str, str]:
    """Do nothing, cheaply.

    The value is entirely in the request having arrived: it prevents the free tier
    suspending the service between judge visits. It deliberately touches no tables, so
    calling it every ten minutes costs nothing.
    """
    return {"task": "keepalive", "status": "ok"}


@router.post("/refresh-jobs", dependencies=[CronAuth])
async def refresh_jobs(session: SessionDep) -> dict[str, object]:
    """Read every registered board and fold the results into the shared index.

    Returns per-source counts rather than a bare acknowledgement. Story 28: a source that
    fetches successfully and creates nothing for a week is the failure that hides best, so the
    numbers have to come back where a scheduler's logs will keep them.

    Classification runs in the same request as ingestion, and that ordering matters more than it
    looks. The feed's filters are exclusions, so a posting sitting in the index unclassified is
    not merely unsorted — it is invisible to every active filter.

    Dedup runs last, after classification, and that order is also deliberate: it reuses the
    seniority and role family just derived to rule pairs out for free, which is what keeps the
    ambiguous band — the only part of this feature that spends inference — as small as it is.

    **The whole request has a budget, not just each phase.** Every phase was bounded
    individually and nothing bounded their sum, so a slow run could reach roughly nine minutes —
    four for the board sweep, plus classification, plus up to twelve live enrichment calls each
    able to spend six seconds on rate-limit backoff, plus dedup. The scheduled refresh was
    returning **502 after seven minutes** while a manual run of the same code finished in one
    minute forty, because a proxy in front of the container gives up long before the work does.

    A phase-by-phase budget is the wrong instrument for a wall-clock limit imposed from outside.
    So the deadline is shared: the sweep is told how much of the window it may use, and
    enrichment is skipped entirely when too little is left. Skipping it is safe in a way that
    skipping the others is not — with no fresh reading the vocabulary still produces a skill set,
    so scores keep working and simply say which reading produced them, whereas an unclassified
    posting is invisible to every filter in the feed.

    Nothing is lost by stopping early. Boards are swept least-recently-fetched first, so the ones
    a short run misses are the ones the next run begins with, and enrichment picks up where it
    left off because success is what timestamps a posting.
    """
    started = time.monotonic()

    # Leaves room for classification and dedup inside the overall budget. Deliberately well under
    # what the proxy tolerates: the aim is a request that always answers, not one that finishes
    # every board in one go.
    sweep_budget = min(DEFAULT_MAX_SECONDS, _REQUEST_BUDGET_SECONDS * 0.6)

    summary = await refresh_all_boards(session, max_seconds=sweep_budget)
    classified = await classify_stored_jobs(session)

    # Skills are read here rather than at render time, per ADR 0011: the feed is forbidden from
    # calling a model, and the reading is identical for every student so paying for it once per
    # posting is the whole saving. It must follow classification, because which postings are
    # worth reading is decided by the seniority and country classification just derived.
    #
    # An inference client is passed when one is configured. Unlike dedup, this call has a
    # useful fallback: with no key the vocabulary still produces a skill set, so the score
    # works everywhere and simply says which reading produced it.
    remaining = _REQUEST_BUDGET_SECONDS - (time.monotonic() - started)
    enrichment_skipped = remaining < _ENRICHMENT_RESERVE_SECONDS

    if enrichment_skipped:
        logger.info(
            "skipping skill enrichment: %.0fs of budget left, needs %.0fs",
            remaining,
            _ENRICHMENT_RESERVE_SECONDS,
        )
        enriched = EnrichmentSummary()
    else:
        enriched = await enrich_job_skills(session, llm=_optional_llm())

    # No inference client is passed to dedup. Its deterministic bands do the work, and the
    # deployed demo has no key at all — a refresh that needed one would do nothing in the
    # environment the judges use. The ambiguous band degrades to distinct, the safe direction.
    dedup = await deduplicate(session)

    return {
        "task": "refresh-jobs",
        "boards_attempted": summary.boards_attempted,
        "boards_succeeded": summary.boards_succeeded,
        "boards_failed": summary.boards_failed,
        "boards_skipped": summary.boards_skipped,
        # Deferred by backoff rather than broken. A permanently dead company must not consume
        # the run window every day, and must not be reported as a failure it did not have today.
        "boards_backed_off": summary.boards_backed_off,
        "aggregator_attempted": summary.aggregator_attempted,
        "aggregator_succeeded": summary.aggregator_succeeded,
        "created": summary.created,
        "updated": summary.updated,
        "reopened": summary.reopened,
        "closed": summary.closed,
        # Per source, because a total would hide one adapter closing its entire listing behind
        # four that closed nothing. Story 28 wants that visible in the run that causes it.
        "closed_by_source": summary.closed_by_source,
        "aggregator_expired": summary.aggregator_expired,
        # Boards that answered 200 with an empty list while still holding open jobs. Named, not
        # counted: the useful question is which board to go and look at.
        "suspicious_boards": summary.suspicious_boards,
        # True when the run stopped early to stay inside its window. A run that keeps hitting
        # this needs a longer window or fewer boards, and that is invisible if a truncated run
        # looks exactly like a complete one.
        "deadline_reached": summary.deadline_reached,
        "elapsed_seconds": summary.elapsed_seconds,
        "classified": classified,
        # True when there was not enough of the request budget left to read skills. Reported rather
        # than inferred from a zero count, because "read nothing" and "did not run" are different
        # facts and a scheduler's history is the only place anyone will notice the difference.
        "skills_read_skipped_for_budget": enrichment_skipped,
        "skills_read": {
            "considered": enriched.considered,
            "enriched": enriched.enriched,
            "batches": enriched.batches,
            "failed_batches": enriched.failed_batches,
            "added_by_model": enriched.added_by_model,
            "discarded_unevidenced": enriched.discarded,
            "by_basis": enriched.basis_counts,
        },
        "deduplicated": {
            "compared": dedup.compared,
            "collapsed": dedup.collapsed,
            "asked": dedup.asked,
            "undecided": dedup.undecided,
            "decided_by": dedup.decided_by,
        },
    }
