from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, cron, jobs, outreach, resumes, sources, students, tailoring
from app.config import get_settings
from app.db import database_is_reachable, dispose_engine
from app.errors import register_error_handlers


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Release the connection pool on shutdown.

    Not driven by a test — asserting it at the HTTP seam would mean testing
    framework behaviour rather than ours. It is here because the deployment target
    has a low connection ceiling (ADR 0008) and a redeploy that leaks its pool
    would exhaust it after a handful of releases.
    """
    yield
    await dispose_engine()


app = FastAPI(title="Reachly", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)

# The frontend is served from a different host than the API, so the browser needs the
# API to name the origins it will accept. Explicit origins rather than "*", because
# credentials are sent and a wildcard would forbid them anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health(
    database_up: Annotated[bool, Depends(database_is_reachable)],
) -> dict[str, str]:
    """Liveness plus database reachability.

    Always answers 200: the API is demonstrably responding, and a pinger should
    not treat a degraded database as the service being down. The distinction is
    carried in the body so a human reading it learns something.

    The inference configuration is reported too, and it is not decoration. Both values are
    settable per environment, and both have already produced failures that looked like bugs in
    unrelated features: demo mode made a real resume upload fail with a parse error, and a model
    whose free-tier quota had run out made tailoring silently return every bullet unchanged.
    Neither was visible from outside the process. Naming them here turns a confusing symptom into
    a one-request diagnosis.

    No secret is exposed — a model name and a boolean, never the key.
    """
    settings = get_settings()
    return {
        "status": "ok" if database_up else "degraded",
        "database": "up" if database_up else "down",
        "inference": "recorded" if settings.demo_mode else "live",
        "model": settings.gemini_model,
        "key_configured": "yes" if settings.gemini_api_key else "no",
    }


router.include_router(auth.router)
router.include_router(students.router)
router.include_router(resumes.router)
router.include_router(sources.router)
router.include_router(jobs.router)
router.include_router(tailoring.router)
router.include_router(outreach.router)
app.include_router(router)

# Not under /api/v1: these are operational endpoints, not part of the student-facing API.
app.include_router(cron.router)
