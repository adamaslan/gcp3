"""Shared free-text LLM client: OpenRouter with Mistral fallback.

Formerly `gemini_client.py` (Phases 1-2 of
docs/openrouter-migration-and-db-parity-plan.md in nuwrrrld-portal — this
repo doesn't carry its own copy of that plan doc, see the PR description).
All backend modules that need a plain "prompt in, text out" call (as opposed
to the schema-validated `llm/structured_call.py` / `llm/provider_router.py`
path, which is separate, unused scaffolding — see this module's own note at
the bottom) import `call_llm()` from here.

Primary: OpenRouter, a static small fallback chain of $0-priced models (see
_OPENROUTER_MODEL_CHAIN below — mirrors the portal's `FREE_MODEL_CHAIN`
philosophy in `nuwrrrld-portal/lib/openrouter.ts`, but not auto-refreshed;
see this module's "Open question" note).
Fallback: Mistral (`mistral-small-latest`) — used when every OpenRouter model
in the chain fails (401/404/429/5xx).

This file used to be Gemini-primary (`gemini_client.py`, `call_gemini()`,
`GEMINI_API_KEY`). That was live traffic, not dead code — 5 modules
(story_picker, ai_summary, correlation_article, blog_reviewer, daily_blog)
call it on every run. This rewrite keeps the exact same
`async def call_llm(prompt: str) -> str` shape those callers already use, so
none of them needed a logic change, only an import.
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Ordered fallback chain of $0-priced OpenRouter models. Static rather than
# live-refreshed like the portal's FREE_MODEL_CHAIN (nuwrrrld-portal's
# scripts/refresh-free-models.mjs) — see "Open question" below.
_OPENROUTER_MODEL_CHAIN = (
    "qwen/qwen3-235b-a22b:free",
    "qwen/qwen3-30b-a3b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
)
_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL = "mistral-small-latest"
_MAX_ATTEMPTS_PER_MODEL = 2
_BACKOFF_BASE = 5  # seconds; doubles each retry within a model: 5, 10

# Shared client for connection pooling across calls.
_shared_client: httpx.AsyncClient | None = None


def _get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=60)
    return _shared_client


async def _call_mistral(prompt: str) -> str:
    """Send a prompt to Mistral and return the text response.

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

    client = _get_shared_client()
    resp = await client.post(_MISTRAL_URL, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _call_openrouter_model(prompt: str, model: str, api_key: str) -> str:
    """One attempt against one OpenRouter model. Raises on any HTTP error."""
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # OpenRouter attributes free-tier usage by referer/title; harmless if
        # ignored by a given upstream provider.
        "HTTP-Referer": "https://github.com/adamaslan/gcp3",
        "X-Title": "nuwrrrld gcp3 backend",
    }
    client = _get_shared_client()
    resp = await client.post(_OPENROUTER_URL, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _call_openrouter(prompt: str) -> str:
    """Walk the free-model chain; each model gets up to
    _MAX_ATTEMPTS_PER_MODEL tries with backoff on 429 before moving to the
    next model. Raises the last error if every model in the chain fails.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    last_exc: Exception | None = None
    for model in _OPENROUTER_MODEL_CHAIN:
        for attempt in range(1, _MAX_ATTEMPTS_PER_MODEL + 1):
            try:
                text = await _call_openrouter_model(prompt, model, api_key)
                if model != _OPENROUTER_MODEL_CHAIN[0] or attempt > 1:
                    logger.info(
                        "legacy_client: OpenRouter succeeded model=%s attempt=%d", model, attempt
                    )
                return text
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code == 429 and attempt < _MAX_ATTEMPTS_PER_MODEL:
                    wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "legacy_client: OpenRouter 429 model=%s attempt=%d/%d — waiting %ds",
                        model, attempt, _MAX_ATTEMPTS_PER_MODEL, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.warning(
                    "legacy_client: OpenRouter model=%s failed status=%d — trying next model",
                    model, exc.response.status_code,
                )
                break
            except Exception as exc:  # noqa: BLE001 — any failure moves to the next model
                last_exc = exc
                logger.warning("legacy_client: OpenRouter model=%s failed err=%s", model, exc)
                break

    raise RuntimeError(f"All OpenRouter models in the chain failed: {last_exc}")


async def call_llm(prompt: str) -> str:
    """Send a prompt to OpenRouter's free-model chain; falls back to Mistral
    if every model in the chain fails.

    Args:
        prompt: The full text prompt to send.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If OPENROUTER_API_KEY is not set, every model in the
            chain fails, and Mistral fallback also fails (or MISTRAL_KEY is
            unset).
    """
    try:
        return await _call_openrouter(prompt)
    except Exception as exc:
        logger.warning("legacy_client: OpenRouter chain exhausted — falling back to Mistral: %s", exc)

    try:
        result = await _call_mistral(prompt)
        logger.info("legacy_client: Mistral fallback succeeded")
        return result
    except Exception as mistral_exc:
        logger.error("legacy_client: Mistral fallback failed: %s", mistral_exc)
        raise RuntimeError(
            f"OpenRouter chain and Mistral fallback both failed: {mistral_exc}"
        ) from mistral_exc


# ── Note on llm/provider_router.py / llm/structured_call.py ─────────────────
# This module (free-text prompt → text) is deliberately NOT the same code
# path as llm/provider_router.py's `structured_llm_call()` (schema-validated,
# Pydantic-typed output). That gateway currently has no callers anywhere in
# this repo, and its `OpenRouterProvider`/`MistralProvider`/`GeminiProvider`
# classes in llm/providers/ are unimplemented stubs that always raise —
# provider_router.py's own DisabledProvider wrapper never even reaches them,
# always failing to `ai_degraded=True`. Wiring that gateway up is a separate,
# larger task (needs a `request` dict shape design, since none exists yet,
# and a decision on structured-JSON-mode support per model) — out of scope
# here; this file only replaces the free-text Gemini path.
