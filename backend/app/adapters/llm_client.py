"""The inference seam.

Reachly carries its own provider. ADR 0002: Kiro built this project and does not run
inside it — its subscription terms cover automation in software development, not serving
an application's end users. Gemini's free tier needs no credit card.

One protocol, two implementations, selected by `DEMO_MODE`. Every call site depends on
the protocol, so the keyless path is not a special case bolted on for judges — it is the
default.
"""

from typing import Protocol

from app.config import get_settings
from app.errors import DomainError


class LLMError(DomainError):
    """Base for inference failures. Never raised directly."""

    status_code = 502
    code = "llm_error"


class LLMUnavailable(LLMError):
    """The provider could not be reached, refused the request, or timed out.

    Includes rate limiting. Distinct from a malformed reply, because this one may well
    succeed on a retry and the other will not.
    """

    code = "llm_unavailable"
    message = "The writing service is busy. Try again in a moment."


class LLMMalformedResponse(LLMError):
    """The provider replied, but not with what was asked for.

    Retrying is unlikely to help, so the caller should fail rather than loop.
    """

    code = "llm_malformed_response"
    message = "The writing service returned something unusable."


class LLMClient(Protocol):
    """Single-turn JSON completion.

    JSON rather than free text because every use in Reachly parses the result. Asking
    for prose and then extracting structure from it adds a failure mode for nothing.
    """

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, object]:
        """Return the parsed JSON object, or raise an `LLMError` subclass."""
        ...


def get_llm_client() -> LLMClient:
    """The client for the current configuration.

    `DEMO_MODE` selects recorded responses, and it wins over a configured key. That ordering is
    deliberate and was briefly reversed by mistake: preferring the key meant the test suite began
    constructing a real client and reaching the network, breaking the invariant that tests never
    call an external API.

    The consequence for deployment is a configuration decision rather than a code one. A
    deployment that has a key should run with `DEMO_MODE=false` so real resumes parse properly; a
    deployment without one runs in demo mode and serves recorded responses. Inferring that from the
    presence of a key would take the choice away from whoever configured the environment.

    A missing key outside demo mode stays a hard error rather than a silent degrade. A deployment
    that appears to work while every request returns a fixture is exactly the deception ADR 0006
    exists to prevent.
    """
    from app.adapters.fixture_llm_client import FixtureLLMClient
    from app.adapters.gemini_client import GeminiClient

    settings = get_settings()
    if settings.demo_mode:
        return FixtureLLMClient()

    if not settings.gemini_api_key:
        raise LLMUnavailable("No inference provider is configured.")
    return GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
