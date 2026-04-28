"""Shared LLM client: Gemini 2.0 Flash with Mistral fallback.

All backend modules that call Gemini import call_gemini() from here.
Centralises: API key handling, retry logic, backoff, logging.

Primary: Gemini 2.0 Flash — 15 RPM free tier.
Fallback: Mistral (mistral-small-latest) — used when Gemini exhausts 3 retries.
Backoff schedule for Gemini: 10s → 20s → 40s (doubles each attempt).
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
_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL = "mistral-small-latest"
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 10  # seconds; doubles each retry: 10, 20, 40


async def _call_mistral(prompt: str) -> str:
    """Send a prompt to Mistral and return the text response.

    Args:
        prompt: The full text prompt to send.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If MISTRAL_KEY is not set.
        httpx.HTTPStatusError: On HTTP errors.
    """
    api_key = os.environ.get("MISTRAL_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_KEY not set — cannot fall back to Mistral")

    payload = {
        "model": _MISTRAL_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(_MISTRAL_URL, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def call_gemini(prompt: str) -> str:
    """Send a prompt to Gemini 2.0 Flash; falls back to Mistral on quota exhaustion.

    Retries Gemini up to 3 times on 429 with exponential backoff (10s, 20s, 40s).
    If all Gemini retries fail with 429, attempts Mistral as a fallback before raising.

    Args:
        prompt: The full text prompt to send.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If GEMINI_API_KEY is not set, all retries exhausted, and
            Mistral fallback also fails.
        httpx.HTTPStatusError: On non-429 HTTP errors from Gemini.
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

    # Gemini quota exhausted — try Mistral before giving up
    logger.warning(
        "gemini_client: Gemini exhausted %d retries — falling back to Mistral",
        _MAX_ATTEMPTS,
    )
    try:
        result = await _call_mistral(prompt)
        logger.info("gemini_client: Mistral fallback succeeded")
        return result
    except Exception as mistral_exc:
        logger.error("gemini_client: Mistral fallback failed: %s", mistral_exc)

    raise RuntimeError(
        f"Gemini call failed after {_MAX_ATTEMPTS} attempts (rate limited): {last_exc}"
    )
