"""Model pricing config and cost computation (Weakness #10)."""
from __future__ import annotations

MODEL_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.0-flash": {
        "input_per_1m_usd": 0.10,
        "output_per_1m_usd": 0.40,
        "cached_input_per_1m_usd": 0.025,
        "grounded_surcharge_per_request_usd": 0.0,  # free tier
    },
    "gemini-2.0-flash-lite": {
        "input_per_1m_usd": 0.075,
        "output_per_1m_usd": 0.30,
        "cached_input_per_1m_usd": 0.01875,
        "grounded_surcharge_per_request_usd": 0.0,
    },
    "gemini-1.5-flash": {
        "input_per_1m_usd": 0.075,
        "output_per_1m_usd": 0.30,
        "cached_input_per_1m_usd": 0.01875,
        "grounded_surcharge_per_request_usd": 0.0,
    },
    "gemini-1.5-pro": {
        "input_per_1m_usd": 1.25,
        "output_per_1m_usd": 5.00,
        "cached_input_per_1m_usd": 0.3125,
        "grounded_surcharge_per_request_usd": 0.035,
    },
}

DEFAULT_MODEL = "gemini-2.0-flash"


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
        grounded: Whether Google Search grounding surcharge applies.

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
