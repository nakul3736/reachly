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

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.services.ingest_service import refresh_all_boards
from app.services.job_service import classify_stored_jobs

router = APIRouter(prefix="/internal/cron", tags=["internal"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


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
    """
    summary = await refresh_all_boards(session)
    classified = await classify_stored_jobs(session)

    return {
        "task": "refresh-jobs",
        "boards_attempted": summary.boards_attempted,
        "boards_succeeded": summary.boards_succeeded,
        "boards_failed": summary.boards_failed,
        "boards_skipped": summary.boards_skipped,
        "created": summary.created,
        "updated": summary.updated,
        "classified": classified,
    }
