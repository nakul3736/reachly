"""The outbound HTTP transport — seam 3.

Every outbound request in this application is made with a client from here, and this is the one
place tests and demo mode substitute. Substituting the *transport* rather than a `JobSource`
protocol is deliberate: provider-JSON normalisation is the code most likely to be wrong in the
job index, and a fixture implementation of a source protocol would replace exactly that. Faking
the socket instead means the adapters, the status handling and the JSON decoding all still run.

That choice was learned rather than reasoned. An earlier fixture resume parser returned a
finished result and skipped extraction, evidence checking and identifier derivation, so anyone
running in demo mode exercised a different program from production.

It also exists because of a smaller mistake: the refresh endpoint used to construct its own
client, which meant the test suite quietly made live requests to The Muse. Tests must never
reach an external API, and a single factory is what makes that enforceable rather than a habit.
"""

from collections.abc import Callable

import httpx

# Long enough for a slow board, short enough that one hung provider cannot consume the whole
# refresh window on a free host.
DEFAULT_TIMEOUT = 30.0

_factory: Callable[[], httpx.AsyncClient] | None = None


def get_http_client() -> httpx.AsyncClient:
    """A client for outbound requests, or whatever has been substituted for one."""
    if _factory is not None:
        return _factory()
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        # Providers redirect between www and apex hosts; without this a board looks like a 301
        # failure rather than a board.
        follow_redirects=True,
        headers={"User-Agent": "Reachly/0.1 (+https://github.com/nakul3736/reachly)"},
    )


def set_http_client_factory(factory: Callable[[], httpx.AsyncClient] | None) -> None:
    """Substitute the transport. Intended for tests and for demo-mode fixtures."""
    global _factory
    _factory = factory
