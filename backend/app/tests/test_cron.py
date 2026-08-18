"""The externally triggered cron endpoints.

Kept to the security-relevant behaviour: who is allowed in, and what an outsider learns.
Per ADR 0007 these endpoints are reachable from the public internet, so this is not a
path to leave untested.
"""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient

KEEPALIVE = "/internal/cron/keepalive"
SECRET = "test-cron-secret"


@pytest.fixture(autouse=True)
def _cron_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CRON_SECRET", SECRET)
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    # Cleared on the way out too: a cached Settings carrying the test secret would leak
    # into any later test that reads configuration.
    get_settings.cache_clear()


async def test_the_correct_secret_is_accepted(client: AsyncClient) -> None:
    response = await client.post(KEEPALIVE, headers={"X-Cron-Secret": SECRET})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Cron-Secret": ""}, {"X-Cron-Secret": "wrong"}],
    ids=["absent", "empty", "wrong"],
)
async def test_a_bad_secret_is_indistinguishable_from_a_missing_route(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    """404, not 401.

    A 401 confirms the endpoint exists, which tells a scanner there is something here
    worth attacking. Without the secret this path should look like a typo.
    """
    response = await client.post(KEEPALIVE, headers=headers)

    assert response.status_code == 404


async def test_an_unconfigured_secret_fails_closed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deployment that forgot to set the secret must not expose the endpoints.

    The dangerous implementation is "no secret configured means no check required",
    which is the exact shape of an accidental public trigger for our outbound budget.
    """
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    response = await client.post(KEEPALIVE, headers={"X-Cron-Secret": SECRET})

    assert response.status_code == 404
