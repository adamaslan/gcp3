"""3-tier LLM wrapper for structured output (Weakness #7).

Tier 1: native response_schema constrained decoding via google-genai SDK.
Tier 2: single retry with validation-error feedback injected into prompt.
Tier 3: rule-based fallback — sets ai_degraded=True, logs warning.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Type, TypeVar

from pydantic import BaseModel, ValidationError

from llm.cost_logger import log_llm_call
from llm.pricing import DEFAULT_MODEL

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

ALLOWED_MODELS = (
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
)


@dataclass
class StructuredResult:
    data: Any
    tier_used: int
    ai_degraded: bool
    validation_retries: int
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    model: str = DEFAULT_MODEL
    error: str | None = None


def _call_gemini_raw(
    prompt: str,
    model: str,
    response_schema: dict | None,
    *,
    grounded: bool = False,
) -> tuple[str, int, int, int]:
    """Call Gemini and return (text, input_tokens, output_tokens, cached_tokens).

    Raises on any API error.
    """
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        raise RuntimeError("google-generativeai package not installed")

    generation_config: dict[str, Any] = {"temperature": 0.1}
    if response_schema is not None:
        generation_config["response_mime_type"] = "application/json"
        generation_config["response_schema"] = response_schema

    tools = []
    if grounded:
        tools.append({"google_search_retrieval": {}})

    gemini_model = genai.GenerativeModel(
        model_name=model,
        generation_config=generation_config,
        tools=tools or None,
    )
    response = gemini_model.generate_content(prompt)
    text = response.text or ""
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", 0) or 0
    output_tokens = getattr(usage, "candidates_token_count", 0) or 0
    cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0
    return text, input_tokens, output_tokens, cached_tokens


def structured_generate(
    prompt: str,
    schema: Type[T],
    endpoint: str,
    *,
    ticker: str | None = None,
    model: str = DEFAULT_MODEL,
    prompt_version: str = "unknown",
    fallback_fn: Any = None,
) -> StructuredResult:
    """Generate a structured Pydantic output with 3-tier fallback.

    Args:
        prompt: Full prompt string.
        schema: Pydantic model class for the expected output.
        endpoint: Caller endpoint name (for cost logging).
        ticker: Ticker symbol for logging.
        model: Gemini model ID.
        prompt_version: Prompt version tag.
        fallback_fn: Callable() -> dict for rule-based Tier 3 fallback.

    Returns:
        StructuredResult with parsed data and metadata.
    """
    if model not in ALLOWED_MODELS:
        logger.warning("Unknown model %s, falling back to %s", model, DEFAULT_MODEL)
        model = DEFAULT_MODEL

    schema_dict = schema.model_json_schema()
    t0 = time.perf_counter()

    # Tier 1: native constrained decoding
    try:
        text, in_tok, out_tok, cached_tok = _call_gemini_raw(prompt, model, schema_dict)
        parsed = schema.model_validate_json(text)
        latency_ms = (time.perf_counter() - t0) * 1000
        log_llm_call(
            endpoint=endpoint, ticker=ticker, model=model, prompt_version=prompt_version,
            grounded=False, input_tokens=in_tok, output_tokens=out_tok,
            cached_input_tokens=cached_tok, latency_ms=latency_ms,
            tier_used=1, validation_retries=0, cache_hit=False,
        )
        return StructuredResult(
            data=parsed, tier_used=1, ai_degraded=False, validation_retries=0,
            latency_ms=latency_ms, input_tokens=in_tok, output_tokens=out_tok,
            cached_input_tokens=cached_tok, model=model,
        )
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        first_error = str(e)
        logger.warning("structured_generate tier1 failed endpoint=%s error=%s", endpoint, first_error)

    # Tier 2: retry with validation error in prompt
    try:
        retry_prompt = (
            f"{prompt}\n\n"
            f"[VALIDATION ERROR FROM PREVIOUS ATTEMPT — fix these issues and try again]\n{first_error}\n"
            f"Return ONLY valid JSON matching the schema."
        )
        text, in_tok, out_tok, cached_tok = _call_gemini_raw(retry_prompt, model, schema_dict)
        parsed = schema.model_validate_json(text)
        latency_ms = (time.perf_counter() - t0) * 1000
        log_llm_call(
            endpoint=endpoint, ticker=ticker, model=model, prompt_version=prompt_version,
            grounded=False, input_tokens=in_tok, output_tokens=out_tok,
            cached_input_tokens=cached_tok, latency_ms=latency_ms,
            tier_used=2, validation_retries=1, cache_hit=False,
        )
        return StructuredResult(
            data=parsed, tier_used=2, ai_degraded=False, validation_retries=1,
            latency_ms=latency_ms, input_tokens=in_tok, output_tokens=out_tok,
            cached_input_tokens=cached_tok, model=model,
        )
    except Exception as e2:
        logger.warning("structured_generate tier2 failed endpoint=%s error=%s", endpoint, str(e2))

    # Tier 3: rule-based fallback
    latency_ms = (time.perf_counter() - t0) * 1000
    fallback_data: Any = None
    fallback_error: str | None = None
    if fallback_fn is not None:
        try:
            raw = fallback_fn()
            fallback_data = schema.model_validate(raw)
        except Exception as e3:
            fallback_error = str(e3)
            logger.error("structured_generate tier3 fallback also failed endpoint=%s error=%s", endpoint, fallback_error)
    else:
        fallback_error = "no fallback_fn provided"

    log_llm_call(
        endpoint=endpoint, ticker=ticker, model=model, prompt_version=prompt_version,
        grounded=False, input_tokens=0, output_tokens=0,
        cached_input_tokens=0, latency_ms=latency_ms,
        tier_used=3, validation_retries=1, cache_hit=False,
    )
    logger.warning("structured_generate degraded to tier3 endpoint=%s ticker=%s", endpoint, ticker)
    return StructuredResult(
        data=fallback_data, tier_used=3, ai_degraded=True, validation_retries=1,
        latency_ms=latency_ms, input_tokens=0, output_tokens=0,
        model=model, error=fallback_error,
    )
