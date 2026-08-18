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
