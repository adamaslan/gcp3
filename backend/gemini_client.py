"""Shared Gemini client with retry and exponential backoff.

All backend modules that call Gemini import call_gemini() from here.
Centralises: API key handling, retry logic, backoff, logging.

Rate limit: 15 RPM free tier. On 429 we back off and retry up to 3 times.
Backoff schedule: 10s → 20s → 40s (doubles each attempt).
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 10  # seconds; doubles each retry: 10, 20, 40


async def call_gemini(prompt: str) -> str:
    """Send a prompt to Gemini 2.0 Flash and return the text response.

    Retries up to 3 times on 429 with exponential backoff (10s, 20s, 40s).
    Raises RuntimeError on non-retryable errors or exhausted retries.

    Args:
        prompt: The full text prompt to send.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If GEMINI_API_KEY is not set, or all retries exhausted.
        httpx.HTTPStatusError: On non-429 HTTP errors (4xx/5xx).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {"x-goog-api-key": api_key}

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(_GEMINI_URL, json=payload, headers=headers)
                if resp.status_code == 429:
                    wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "gemini_client: 429 rate limit attempt=%d/%d — waiting %ds",
                        attempt, _MAX_ATTEMPTS, wait,
                    )
                    await asyncio.sleep(wait)
                    last_exc = httpx.HTTPStatusError(
                        f"429 Too Many Requests (attempt {attempt})",
                        request=resp.request,
                        response=resp,
                    )
                    continue
                resp.raise_for_status()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                if attempt > 1:
                    logger.info("gemini_client: succeeded on attempt=%d", attempt)
                return text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "gemini_client: 429 rate limit attempt=%d/%d — waiting %ds",
                    attempt, _MAX_ATTEMPTS, wait,
                )
                await asyncio.sleep(wait)
                last_exc = exc
                continue
            raise

    raise RuntimeError(
        f"Gemini call failed after {_MAX_ATTEMPTS} attempts (rate limited): {last_exc}"
    )
