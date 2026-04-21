"""Multi-timeframe signal matrix (Weakness #3).

Per-timeframe calls routed through structured_generate.
Cache TTLs: 1M/3M/6M/1Y at 4h/12h/24h/24h; 1D/5D always fresh.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from schemas.signal_output import (
    DivergencePattern,
    Evidence,
    EvidenceItem,
    EvidenceSource,
    Signal,
    SignalDirection,
    Timeframe,
    TimeframeMatrix,
    alignment_score,
    classify_divergence,
)
from llm.structured_call import structured_generate
from llm.pricing import DEFAULT_MODEL

logger = logging.getLogger(__name__)

TIMEFRAME_CACHE_TTL_SECONDS: dict[str, int] = {
    "1D": 0,         # always fresh
    "5D": 0,
    "1M": 4 * 3600,
    "3M": 12 * 3600,
    "6M": 24 * 3600,
    "1Y": 24 * 3600,
}

DIVERGENCE_INTERPRETATIONS: dict[str, str] = {
    "aligned_bullish": "All timeframes agree bullish — high conviction setup.",
    "aligned_bearish": "All timeframes agree bearish — high conviction breakdown.",
    "short_bull_long_bear": "Short-term pop within a longer-term downtrend. Potential bear-market rally; caution on entries.",
    "short_bear_long_bull": "Short-term pullback within a longer-term uptrend. Potential buy-the-dip opportunity.",
    "mixed": "Conflicting signals across timeframes — reduce position size or wait for resolution.",
    "insufficient_data": "Not enough timeframe data to classify divergence.",
}

PROMPT_TEMPLATE = """You are a quantitative equity analyst. Produce a structured signal for {ticker} on the {timeframe} timeframe.

Features:
{features_block}

Return JSON matching this schema:
- direction: one of strong_buy|buy|hold|sell|strong_sell
- confidence: float strictly between 0 and 1 (never 0.0 or 1.0)
- evidence items: list of objects with source, weight (supporting weights sum to 1.0), summary, is_counter
  - At least 1 counter item required if confidence > 0.6
  - hold signals must have confidence ≤ 0.75

Respond with JSON only.
"""


def _features_block(features: dict[str, Any]) -> str:
    lines = []
    for k, v in features.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _fallback_signal(timeframe: str, features: dict[str, Any]) -> dict:
    pct = features.get("change_pct", 0)
    if pct > 2:
        direction = "buy"
        confidence = 0.55
    elif pct < -2:
        direction = "sell"
        confidence = 0.55
    else:
        direction = "hold"
        confidence = 0.30
    return {
        "direction": direction,
        "confidence": confidence,
        "timeframe": timeframe,
        "evidence": {
            "items": [
                {
                    "source": "rule_based",
                    "weight": 1.0,
                    "summary": f"Rule-based fallback: change_pct={pct:.2f}%",
                    "is_counter": False,
                }
            ]
        },
        "ai_degraded": True,
        "prompt_version": "fallback_v1",
    }


async def _compute_single_timeframe(
    ticker: str,
    timeframe: str,
    features: dict[str, Any],
    model: str,
    prompt_version: str,
) -> Signal | None:
    cache_key = f"mtf:{ticker}:{timeframe}"
    ttl = TIMEFRAME_CACHE_TTL_SECONDS.get(timeframe, 0)

    if ttl > 0:
        try:
            from firestore import get_cache
            cached = get_cache(cache_key)
            if cached:
                logger.info("mtf_cache_hit ticker=%s tf=%s", ticker, timeframe)
                return Signal.model_validate(cached)
        except Exception as e:
            logger.warning("mtf_cache_read_failed ticker=%s tf=%s error=%s", ticker, timeframe, e)

    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker,
        timeframe=timeframe,
        features_block=_features_block(features),
    )

    result = structured_generate(
        prompt=prompt,
        schema=Signal,
        endpoint="signals",
        ticker=ticker,
        model=model,
        prompt_version=prompt_version,
        fallback_fn=lambda: _fallback_signal(timeframe, features),
    )

    if result.data is None:
        logger.warning("mtf_signal_none ticker=%s tf=%s", ticker, timeframe)
        return None

    signal: Signal = result.data

    if ttl > 0 and not result.ai_degraded:
        try:
            from firestore import set_cache
            set_cache(cache_key, signal.model_dump(), ttl_seconds=ttl)
        except Exception as e:
            logger.warning("mtf_cache_write_failed ticker=%s tf=%s error=%s", ticker, timeframe, e)

    return signal


async def build_timeframe_matrix(
    ticker: str,
    features_by_timeframe: dict[str, dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    prompt_version: str = "mtf_v1",
) -> TimeframeMatrix:
    """Build a TimeframeMatrix by calling the LLM per timeframe concurrently.

    Args:
        ticker: Stock symbol.
        features_by_timeframe: Map of timeframe string to feature dict.
        model: Gemini model ID.
        prompt_version: Prompt version tag.

    Returns:
        TimeframeMatrix with signals, alignment score, and divergence pattern.
    """
    tasks = {
        tf: _compute_single_timeframe(ticker, tf, feats, model, prompt_version)
        for tf, feats in features_by_timeframe.items()
    }

    results: dict[str, Signal | None] = {}
    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for tf, result in zip(tasks.keys(), gathered):
        if isinstance(result, Exception):
            logger.error("mtf_timeframe_error ticker=%s tf=%s error=%s", ticker, tf, result)
            results[tf] = None
        else:
            results[tf] = result

    valid_signals = {tf: s for tf, s in results.items() if s is not None}
    signal_list = list(valid_signals.values())

    align = alignment_score(signal_list) if signal_list else 0.0
    div_pattern = classify_divergence(valid_signals) if valid_signals else DivergencePattern.insufficient_data
    div_interp = DIVERGENCE_INTERPRETATIONS.get(div_pattern.value, "")

    return TimeframeMatrix(
        ticker=ticker,
        signals=valid_signals,
        alignment_score=align,
        divergence_pattern=div_pattern,
        divergence_interpretation=div_interp,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )
