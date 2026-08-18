"""Gemini, over its REST API.

httpx directly rather than the `google-generativeai` SDK: the SDK is a large dependency
for one endpoint, and the payload shape here is small enough to be clearer written out
than configured. Fewer dependencies also means a smaller container and less to audit.
"""

import asyncio
import json
import logging
from typing import Any

import httpx

from app.adapters.llm_client import LLMMalformedResponse, LLMUnavailable

logger = logging.getLogger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Three attempts spanning roughly 6 seconds of waiting. Enough to clear a per-minute
# rate limit spike without leaving a student watching a spinner.
_MAX_ATTEMPTS = 3
_BASE_DELAY_SECONDS = 2.0


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

        # The free tier limits requests per minute, and a student uploading a resume
        # should not fail because someone else uploaded one seconds earlier. Retried only
        # for conditions that can actually change: rate limits and server errors. A
        # refused request is never retried, because a bad key or a retired model will
        # refuse just as firmly the second time.
        last_error: LLMUnavailable | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return await self._attempt(payload)
            except LLMUnavailable as exc:
                last_error = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    break
                delay = _BASE_DELAY_SECONDS * (2**attempt)
                logger.warning(
                    "inference provider unavailable, retrying in %.1fs (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)

        raise last_error if last_error else LLMUnavailable

    async def _attempt(self, payload: dict[str, Any]) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    _ENDPOINT.format(model=self._model),
                    params={"key": self._api_key},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            # Timeouts, DNS failures, connection resets. All worth retrying.
            raise LLMUnavailable from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise LLMUnavailable
        if response.status_code != 200:
            # 400, 403 and 404 are our fault — a bad key, a malformed request, or a model
            # name that has been retired. Retrying fixes none of them.
            #
            # The provider's own message is logged, because without it a retired model
            # name is indistinguishable from a bad key: both are just "it failed". This
            # was not hypothetical — a stale pinned model produced exactly that dead end,
            # and finding the cause needed a throwaway script instead of a log line.
            logger.error(
                "inference provider refused: status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
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
