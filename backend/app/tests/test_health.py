"""Health endpoint.

The keep-alive triggers in ADR 0007 call this every ten minutes to stop the free
tier sleeping, so it must stay cheap and must not query application tables.

It always answers 200 so a pinger does not treat a degraded database as an
outage of the service itself; the distinction is carried in the body.
"""

from httpx import ASGITransport, AsyncClient

from app.db import database_is_reachable
from app.main import app


async def _get_health() -> tuple[int, dict[str, str]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    return response.status_code, response.json()


async def test_health_returns_ok() -> None:
    status_code, body = await _get_health()

    assert status_code == 200
    assert body["status"] == "ok"


async def test_health_reports_database_up_when_reachable() -> None:
    status_code, body = await _get_health()

    assert status_code == 200
    assert body["database"] == "up"


async def test_health_reports_degraded_when_database_unreachable() -> None:
    app.dependency_overrides[database_is_reachable] = lambda: False
    try:
        status_code, body = await _get_health()
    finally:
        app.dependency_overrides.clear()

    # Still 200: the API itself is answering. The body carries the bad news.
    assert status_code == 200
    assert body["database"] == "down"
    assert body["status"] == "degraded"
