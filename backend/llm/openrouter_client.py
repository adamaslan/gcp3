"""OpenRouter chat-completions client — the single replacement for Gemini.

Three call sites needed Gemini and each had its own `import
google.generativeai`: `llm/structured_call.py` (schema-constrained JSON),
`llm/grounded_call.py` (web-grounded text with citations) and
`agents/base.py` (multi-turn ReAct chat). They now all come through here.

Two entry points, because the callers differ and neither can change shape:
`complete()` is async for `agents/base.py`; `complete_sync()` is sync because
`structured_generate` and `generate_grounded` are invoked through
`asyncio.to_thread` (see `signals/multi_timeframe.py`) and turning them async
would ripple through their callers for no benefit.

Free-text prompts continue to go through `llm/legacy_client.py`, which owns
the same model chain — this module is the source of truth for it, and that
module imports it rather than keeping a second copy.

Why the whole Gemini family had to go: as of 2026-09-10 the `gemini-2.0-*`
and `gemini-1.5-*` models return 404 from generativelanguage.googleapis.com.
Google retired them, and the code had those IDs hardcoded in eight places.
An OpenRouter chain of $0-priced models has the same cost profile as the
Gemini free tier and does not pin us to one vendor's lifecycle.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

URL = "https://openrouter.ai/api/v1/chat/completions"

# Ordered chain of $0-priced models. First is the default; later entries are
# tried when an earlier one 429s past its retries or errors. Kept in sync with
# the portal's FREE_MODEL_CHAIN philosophy (nuwrrrld-portal/lib/openrouter.ts)
# but static — see the "Open question" note in llm/legacy_client.py.
# Verified 2026-09-10 against the live /models list and a real json_schema
# request each: all three return 200 and honor response_format. The previous
# qwen3/llama-3.3 chain 404s in its entirety — the same retired-model-id
# failure that took Gemini out, which is why the chain is now checked rather
# than assumed, and why entries 1 and 2 are deliberately from different
# providers so one provider's outage cannot empty the chain.
MODEL_CHAIN: tuple[str, ...] = (
    "nvidia/nemotron-3-super-120b-a12b:free",   # 120B, 262k ctx
    "nex-agi/nex-n2.5-pro:free",                # different provider
    "nvidia/nemotron-3.5-lightning:free",       # 1M ctx, fastest
)
DEFAULT_MODEL = MODEL_CHAIN[0]

# OpenRouter performs web search for any model when ":online" is appended.
# This is the analog of Gemini's google_search_retrieval tool.
ONLINE_SUFFIX = ":online"

MAX_ATTEMPTS_PER_MODEL = 2
BACKOFF_BASE_SECONDS = 5  # doubles per retry within a model: 5, 10
DEFAULT_TIMEOUT_SECONDS = 60.0

# OpenRouter attributes free-tier usage by referer/title; harmless if a given
# upstream provider ignores them.
_HEADERS_EXTRA = {
    "HTTP-Referer": "https://github.com/adamaslan/gcp3",
    "X-Title": "nuwrrrld gcp3 backend",
}


class OpenRouterError(RuntimeError):
    """Every model in the chain failed, or no API key is configured."""


class EmptyCompletion(OpenRouterError):
    """The model returned 200 with no content.

    Observed with reasoning models in this chain: the whole turn lands in the
    `reasoning` field and `content` comes back "". `reasoning` is the model
    thinking out loud, not an answer, so it is not a usable substitute —
    the right response is to treat this as a failed attempt and let the next
    model in the chain answer.
    """


@dataclass(frozen=True)
class LLMResponse:
    """Vendor-neutral result. Mirrors what the Gemini paths used to read off
    `response.usage_metadata`, minus cached-token counts: OpenRouter does not
    report a cache-hit token split, so `cached_input_tokens` is always 0 at
    the call sites and priced accordingly.
    """
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    citations: list[dict] = field(default_factory=list)


def _headers() -> dict[str, str]:
    """Auth + attribution headers. Raises if no key is configured."""
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        **_HEADERS_EXTRA,
    }


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise OpenRouterError("OPENROUTER_API_KEY not set")
    return key


def _payload(
    messages: Sequence[dict[str, Any]],
    model: str,
    response_schema: dict | None,
    temperature: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "temperature": temperature,
    }
    if response_schema is not None:
        # OpenRouter normalizes this to each upstream provider's structured
        # -output mechanism. Models that cannot honor it still return JSON in
        # content because the prompt asks for it, and the caller validates —
        # so a provider without native support degrades rather than fails.
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": True,
                "schema": response_schema,
            },
        }
    return payload


def _strip_fences(text: str) -> str:
    """Some models wrap JSON in ```json ... ``` despite response_format."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    body = text.split("\n", 1)[-1] if "\n" in text else ""
    return body.rsplit("```", 1)[0].strip()


def _citations_from(message: dict[str, Any]) -> list[dict]:
    """Map OpenRouter `annotations` to the citation shape grounded_call.py
    already consumes: {uri, title, domain, retrieved_at}.
    """
    citations: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for ann in message.get("annotations") or []:
        if ann.get("type") != "url_citation":
            continue
        cite = ann.get("url_citation") or {}
        uri = cite.get("url", "")
        if not uri:
            continue
        try:
            domain = urlparse(uri).netloc
        except Exception:  # noqa: BLE001 — a malformed URI still counts as a citation
            domain = ""
        citations.append({
            "uri": uri,
            "title": cite.get("title", ""),
            "domain": domain,
            "retrieved_at": now,
        })
    return citations


def _parse(data: dict[str, Any], model: str) -> LLMResponse:
    message = (data.get("choices") or [{}])[0].get("message") or {}
    usage = data.get("usage") or {}
    text = _strip_fences(message.get("content") or "")
    if not text:
        raise EmptyCompletion(f"{model} returned empty content")
    return LLMResponse(
        text=text,
        # Report the model OpenRouter actually served, when it says so — the
        # chain means the served model is not always the one requested.
        model=data.get("model") or model,
        input_tokens=usage.get("prompt_tokens") or 0,
        output_tokens=usage.get("completion_tokens") or 0,
        citations=_citations_from(message),
    )


def _models(online: bool) -> tuple[str, ...]:
    if not online:
        return MODEL_CHAIN
    return tuple(m + ONLINE_SUFFIX for m in MODEL_CHAIN)


def _retry_wait(exc: Exception, attempt: int) -> float | None:
    """Seconds to wait before retrying the same model, or None to move on.

    Only 429 is worth retrying against the same model — a 401 is a bad key, a
    404 is a retired model id (the failure that caused this whole migration),
    and a 5xx is faster to route around than to wait out.
    """
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    if exc.response.status_code != 429 or attempt >= MAX_ATTEMPTS_PER_MODEL:
        return None
    return float(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))


def _log_giving_up(model: str, exc: Exception) -> None:
    if isinstance(exc, httpx.HTTPStatusError):
        logger.warning(
            "openrouter: model=%s failed status=%d - trying next model",
            model, exc.response.status_code,
        )
    else:
        logger.warning("openrouter: model=%s failed err=%s", model, exc)


def _log_recovered(model: str, models: tuple[str, ...], attempt: int) -> None:
    if model != models[0] or attempt > 1:
        logger.info("openrouter: succeeded model=%s attempt=%d", model, attempt)


def complete_sync(
    messages: Sequence[dict[str, Any]],
    *,
    response_schema: dict | None = None,
    online: bool = False,
    temperature: float = 0.1,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> LLMResponse:
    """Blocking completion. For callers already running in a worker thread."""
    headers = _headers()
    models = _models(online)
    last_exc: Exception | None = None

    with httpx.Client(timeout=timeout) as client:
        for model in models:
            for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
                try:
                    resp = client.post(
                        URL,
                        json=_payload(messages, model, response_schema, temperature),
                        headers=headers,
                    )
                    resp.raise_for_status()
                    result = _parse(resp.json(), model)
                    _log_recovered(model, models, attempt)
                    return result
                except Exception as exc:  # noqa: BLE001 - policy decides retry vs. next model
                    last_exc = exc
                    wait = _retry_wait(exc, attempt)
                    if wait is None:
                        _log_giving_up(model, exc)
                        break
                    logger.warning(
                        "openrouter: 429 model=%s attempt=%d/%d - waiting %ss",
                        model, attempt, MAX_ATTEMPTS_PER_MODEL, wait,
                    )
                    time.sleep(wait)

    raise OpenRouterError(f"all OpenRouter models failed: {last_exc}")


async def complete(
    messages: Sequence[dict[str, Any]],
    *,
    response_schema: dict | None = None,
    online: bool = False,
    temperature: float = 0.1,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> LLMResponse:
    """Async completion. Same chain and retry policy as complete_sync."""
    headers = _headers()
    models = _models(online)
    last_exc: Exception | None = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        for model in models:
            for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
                try:
                    resp = await client.post(
                        URL,
                        json=_payload(messages, model, response_schema, temperature),
                        headers=headers,
                    )
                    resp.raise_for_status()
                    result = _parse(resp.json(), model)
                    _log_recovered(model, models, attempt)
                    return result
                except Exception as exc:  # noqa: BLE001 - policy decides retry vs. next model
                    last_exc = exc
                    wait = _retry_wait(exc, attempt)
                    if wait is None:
                        _log_giving_up(model, exc)
                        break
                    logger.warning(
                        "openrouter: 429 model=%s attempt=%d/%d - waiting %ss",
                        model, attempt, MAX_ATTEMPTS_PER_MODEL, wait,
                    )
                    await asyncio.sleep(wait)

    raise OpenRouterError(f"all OpenRouter models failed: {last_exc}")


def json_response(response: LLMResponse) -> Any:
    """Parse a completion's text as JSON, raising ValueError with the offending
    text truncated — the callers all validate against a Pydantic schema next
    and need the raw text in the error to log a useful reason.
    """
    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model returned non-JSON: {response.text[:200]!r}") from exc
