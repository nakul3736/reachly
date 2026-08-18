"""Gemini, over its REST API.

httpx directly rather than the `google-generativeai` SDK: the SDK is a large dependency
for one endpoint, and the payload shape here is small enough to be clearer written out
than configured. Fewer dependencies also means a smaller container and less to audit.
"""

import json
from typing import Any

import httpx

from app.adapters.llm_client import LLMMalformedResponse, LLMUnavailable

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiClient:
    """Single-turn JSON completion against Gemini."""

    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, object]:
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                # Ask for JSON at the API level rather than instructing it in the prompt.
                # The model is then constrained by the decoder instead of by persuasion,
                # which removes the "here is your JSON:" preamble failure entirely.
                "responseMimeType": "application/json",
                # Zero temperature: this is extraction, not writing. Two parses of the
                # same resume should agree, or content-derived bullet ids would drift and
                # stored provenance maps would stop resolving.
                "temperature": 0.0,
                "maxOutputTokens": max_output_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    _ENDPOINT.format(model=self._model),
                    params={"key": self._api_key},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            # Timeouts, DNS failures, connection resets. All worth retrying later.
            raise LLMUnavailable from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise LLMUnavailable
        if response.status_code != 200:
            # 400 and 403 are our fault — a bad key, a malformed request, a blocked
            # model. Retrying will not fix any of them.
            raise LLMMalformedResponse(
                f"Inference provider refused the request ({response.status_code})."
            )

        return _extract_json(response.json())


def _extract_json(body: dict[str, Any]) -> dict[str, object]:
    """Pull the JSON object out of a Gemini response envelope.

    Every failure becomes `LLMMalformedResponse`. A response that was truncated by the
    token limit, or blocked by a safety filter, arrives as a missing field rather than an
    error — so an absent candidate is treated as malformed rather than as empty output.
    """
    try:
        candidate = body["candidates"][0]
        text = candidate["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMMalformedResponse from exc

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMMalformedResponse from exc

    if not isinstance(parsed, dict):
        # A bare list or string is not what any caller here asked for.
        raise LLMMalformedResponse
    return parsed
