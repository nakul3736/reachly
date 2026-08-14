from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI

from app.api import auth, resumes, students
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

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health(
    database_up: Annotated[bool, Depends(database_is_reachable)],
) -> dict[str, str]:
    """Liveness plus database reachability.

    Always answers 200: the API is demonstrably responding, and a pinger should
    not treat a degraded database as the service being down. The distinction is
    carried in the body so a human reading it learns something.
    """
    return {
        "status": "ok" if database_up else "degraded",
        "database": "up" if database_up else "down",
    }


router.include_router(auth.router)
router.include_router(students.router)
router.include_router(resumes.router)
app.include_router(router)
