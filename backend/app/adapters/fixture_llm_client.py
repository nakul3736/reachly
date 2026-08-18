"""The `DEMO_MODE` inference client.

Serves recorded responses so the whole product works with no API key — the path judges
use, and the default rather than a special case.
"""

from typing import Any

from app.adapters.fixtures.recorded_resumes import recorded_structuring
from app.adapters.llm_client import LLMMalformedResponse

_RESUME_MARKER = "Resume text:"


class FixtureLLMClient:
    """Recorded completions, chosen by what the prompt is asking about."""

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, Any]:
        if _RESUME_MARKER in user:
            return recorded_structuring(user)

        # Deliberately loud. A new call site without a recorded fixture must fail here
        # rather than receive an empty object it would misread as a valid empty answer —
        # the steering rule is that every external call ships its demo fixture in the
        # same commit.
        raise LLMMalformedResponse(
            "No recorded response for this prompt. Add one in "
            "app/adapters/fixtures/ before using DEMO_MODE for it."
        )
