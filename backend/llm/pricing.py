"""Model pricing config and cost computation (Weakness #10).

Priced against OpenRouter's free chain plus the Mistral paid fallback. The
previous Gemini rate card was removed with the models themselves — Google
retired the `gemini-2.0-*`/`gemini-1.5-*` ids (404 as of 2026-09-10).

DEFAULT_MODEL is re-exported from llm/openrouter_client.py so the chain has
exactly one definition; importers of llm.pricing.DEFAULT_MODEL keep working.
"""
from __future__ import annotations

from llm.openrouter_client import DEFAULT_MODEL as OPENROUTER_DEFAULT_MODEL

MODEL_PRICING: dict[str, dict[str, float]] = {
    # The chain is $0-priced on OpenRouter's free tier, so every rate is zero
    # and computed cost is zero. The table is kept rather than deleted because
    # compute_cost_usd() and the cost logger are the only place a future move
    # to paid models would need editing — and because a zero here is a stated
    # fact ("this model is free") rather than a missing entry.
    #
    # grounded_surcharge is per-request: OpenRouter's ":online" web search is
    # billed per request, not per token, and is NOT free. $4 per 1000 results
    # at the default 5 results/request => $0.02/request.
    "nvidia/nemotron-3-super-120b-a12b:free": {
        "input_per_1m_usd": 0.0,
        "output_per_1m_usd": 0.0,
        "cached_input_per_1m_usd": 0.0,
        "grounded_surcharge_per_request_usd": 0.02,
    },
    "nex-agi/nex-n2.5-pro:free": {
        "input_per_1m_usd": 0.0,
        "output_per_1m_usd": 0.0,
        "cached_input_per_1m_usd": 0.0,
        "grounded_surcharge_per_request_usd": 0.02,
    },
    "nvidia/nemotron-3.5-lightning:free": {
        "input_per_1m_usd": 0.0,
        "output_per_1m_usd": 0.0,
        "cached_input_per_1m_usd": 0.0,
        "grounded_surcharge_per_request_usd": 0.02,
    },
    # Mistral is the paid fallback llm/legacy_client.py reaches when the whole
    # free chain fails. Rates as published for mistral-small-latest.
    "mistral-small-latest": {
        "input_per_1m_usd": 0.20,
        "output_per_1m_usd": 0.60,
        "cached_input_per_1m_usd": 0.20,
        "grounded_surcharge_per_request_usd": 0.0,
    },
}

DEFAULT_MODEL = OPENROUTER_DEFAULT_MODEL


def compute_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    grounded: bool = False,
) -> float:
    """Compute USD cost for a single LLM call.

    Args:
        model: Model ID key from MODEL_PRICING.
        input_tokens: Non-cached input tokens.
        output_tokens: Output tokens.
        cached_input_tokens: Cache-hit input tokens (billed at reduced rate).
        grounded: Whether the OpenRouter web-search surcharge applies.

    Returns:
        Cost in USD, rounded to 8 decimal places.
    """
    pricing = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
    cost = (
        input_tokens / 1_000_000 * pricing["input_per_1m_usd"]
        + output_tokens / 1_000_000 * pricing["output_per_1m_usd"]
        + cached_input_tokens / 1_000_000 * pricing["cached_input_per_1m_usd"]
    )
    if grounded:
        cost += pricing["grounded_surcharge_per_request_usd"]
    return round(cost, 8)
