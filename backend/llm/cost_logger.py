"""Cost telemetry for LLM calls (Weakness #10).

Structured JSON logs per call; daily quota tracking with alerts at 50/80/95% of free tier.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from llm.pricing import compute_cost_usd

logger = logging.getLogger(__name__)

# Free-tier daily budget ceiling (Gemini Flash free tier ~generous, set conservative USD cap)
FREE_TIER_DAILY_BUDGET_USD = 0.50
ALERT_THRESHOLDS = (0.50, 0.80, 0.95)

# In-memory daily accumulator (resets at UTC midnight via _ensure_day_reset)
_daily_state: dict[str, Any] = {
    "date": None,
    "total_cost_usd": 0.0,
    "call_count": 0,
    "endpoints": {},  # endpoint -> {"cost_usd": float, "calls": int}
    "alerted_thresholds": set(),
}


def _ensure_day_reset() -> None:
    today = date.today().isoformat()
    if _daily_state["date"] != today:
        _daily_state.update({
            "date": today,
            "total_cost_usd": 0.0,
            "call_count": 0,
            "endpoints": {},
            "alerted_thresholds": set(),
        })


def log_llm_call(
    *,
    endpoint: str,
    ticker: str | None,
    model: str,
    prompt_version: str,
    grounded: bool,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    latency_ms: float,
    tier_used: int,
    validation_retries: int,
    cache_hit: bool,
    request_id: str | None = None,
) -> str:
    """Log a single LLM call with cost and usage data.

    Returns:
        request_id used for this call (generated if not provided).
    """
    _ensure_day_reset()

    request_id = request_id or str(uuid.uuid4())
    cost_usd = compute_cost_usd(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        grounded=grounded,
    )

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "endpoint": endpoint,
        "ticker": ticker,
        "model": model,
        "prompt_version": prompt_version,
        "grounded": grounded,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "cost_usd": cost_usd,
        "latency_ms": round(latency_ms, 1),
        "tier_used": tier_used,
        "validation_retries": validation_retries,
        "cache_hit": cache_hit,
    }
    logger.info("llm_call %s", json.dumps(record))

    # Update daily accumulator
    _daily_state["total_cost_usd"] += cost_usd
    _daily_state["call_count"] += 1
    ep = _daily_state["endpoints"].setdefault(endpoint, {"cost_usd": 0.0, "calls": 0})
    ep["cost_usd"] += cost_usd
    ep["calls"] += 1

    # Threshold alerts
    fraction = _daily_state["total_cost_usd"] / FREE_TIER_DAILY_BUDGET_USD
    for threshold in ALERT_THRESHOLDS:
        if fraction >= threshold and threshold not in _daily_state["alerted_thresholds"]:
            _daily_state["alerted_thresholds"].add(threshold)
            logger.warning(
                "llm_cost_alert threshold=%.0f%% daily_cost_usd=%.4f budget_usd=%.2f",
                threshold * 100,
                _daily_state["total_cost_usd"],
                FREE_TIER_DAILY_BUDGET_USD,
            )

    return request_id


def get_daily_stats() -> dict[str, Any]:
    """Return today's aggregated cost and call statistics."""
    _ensure_day_reset()
    return {
        "date": _daily_state["date"],
        "total_cost_usd": round(_daily_state["total_cost_usd"], 6),
        "call_count": _daily_state["call_count"],
        "budget_usd": FREE_TIER_DAILY_BUDGET_USD,
        "budget_used_pct": round(
            _daily_state["total_cost_usd"] / FREE_TIER_DAILY_BUDGET_USD * 100, 2
        ),
        "endpoints": dict(_daily_state["endpoints"]),
    }


def top_endpoints_by_cost(n: int = 5) -> list[dict[str, Any]]:
    """Return top N endpoints sorted by cumulative cost today."""
    _ensure_day_reset()
    ranked = sorted(
        [{"endpoint": k, **v} for k, v in _daily_state["endpoints"].items()],
        key=lambda x: x["cost_usd"],
        reverse=True,
    )
    return ranked[:n]
