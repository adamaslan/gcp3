"""Feature #17 — Timeframe Alignment Score.

Aggregates per-timeframe signals into:
  - alignment_score (max(bull,bear) / (bull+bear))
  - weighted_alignment_score (confidence-weighted)
  - pattern classification
  - conviction tier

Pure computation over existing TimeframeMatrix — no new data source.
"""
import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

Signal = Literal["strong_buy", "buy", "hold", "sell", "strong_sell"]
Timeframe = Literal["1D", "5D", "1M", "3M", "6M", "1Y"]


@dataclass
class AlignmentScore:
    ticker: str
    per_tf_signals: dict[str, str]
    per_tf_confidences: dict[str, float]
    bullish_count: int
    bearish_count: int
    neutral_count: int
    alignment_score: float
    weighted_alignment_score: float
    pattern: str
    conviction_tier: Literal["high", "medium", "low", "chop"]


def _is_bull(signal: str) -> bool:
    return signal in ("buy", "strong_buy")


def _is_bear(signal: str) -> bool:
    return signal in ("sell", "strong_sell")


def compute_alignment(
    ticker: str,
    per_tf_signals: dict[str, str],
    per_tf_confidences: dict[str, float],
) -> AlignmentScore:
    """Compute timeframe alignment score and pattern classification.

    Args:
        ticker: Ticker symbol.
        per_tf_signals: Dict of {timeframe: signal}.
        per_tf_confidences: Dict of {timeframe: confidence}.

    Returns:
        AlignmentScore with pattern and conviction tier.
    """
    bull = sum(1 for s in per_tf_signals.values() if _is_bull(s))
    bear = sum(1 for s in per_tf_signals.values() if _is_bear(s))
    neutral = len(per_tf_signals) - bull - bear
    total_dir = bull + bear

    score = max(bull, bear) / total_dir if total_dir > 0 else 0.0

    # Weighted version
    bull_w = sum(
        per_tf_confidences.get(tf, 0.5)
        for tf, s in per_tf_signals.items()
        if _is_bull(s)
    )
    bear_w = sum(
        per_tf_confidences.get(tf, 0.5)
        for tf, s in per_tf_signals.items()
        if _is_bear(s)
    )
    total_w = bull_w + bear_w
    weighted_score = max(bull_w, bear_w) / total_w if total_w > 0 else 0.0

    # Pattern
    short_bull = _is_bull(per_tf_signals.get("1D", "hold")) and _is_bull(per_tf_signals.get("5D", "hold"))
    short_bear = _is_bear(per_tf_signals.get("1D", "hold")) and _is_bear(per_tf_signals.get("5D", "hold"))
    long_bull = _is_bull(per_tf_signals.get("3M", "hold")) and _is_bull(per_tf_signals.get("6M", "hold"))
    long_bear = _is_bear(per_tf_signals.get("3M", "hold")) and _is_bear(per_tf_signals.get("6M", "hold"))

    if score >= 5 / 6 and bull >= bear:
        pattern = "aligned_bullish"
    elif score >= 5 / 6 and bear > bull:
        pattern = "aligned_bearish"
    elif short_bull and long_bear:
        pattern = "short_term_bullish_long_term_bearish"
    elif short_bear and long_bull:
        pattern = "short_term_bearish_long_term_bullish"
    elif 0.4 <= score <= 0.6:
        pattern = "choppy"
    else:
        # Check for early reversal (1M/3M flipping vs 6M/1Y)
        mid_bull = _is_bull(per_tf_signals.get("1M", "hold")) or _is_bull(per_tf_signals.get("3M", "hold"))
        long_dir = per_tf_signals.get("6M", "hold")
        if mid_bull and _is_bear(long_dir):
            pattern = "early_reversal_up"
        elif not mid_bull and _is_bull(long_dir):
            pattern = "early_reversal_down"
        else:
            pattern = "choppy"

    # Conviction tier
    if weighted_score >= 0.8:
        conviction_tier: str = "high"
    elif weighted_score >= 0.6:
        conviction_tier = "medium"
    elif weighted_score >= 0.4:
        conviction_tier = "low"
    else:
        conviction_tier = "chop"

    return AlignmentScore(
        ticker=ticker,
        per_tf_signals=per_tf_signals,
        per_tf_confidences=per_tf_confidences,
        bullish_count=bull,
        bearish_count=bear,
        neutral_count=neutral,
        alignment_score=round(score, 3),
        weighted_alignment_score=round(weighted_score, 3),
        pattern=pattern,
        conviction_tier=conviction_tier,  # type: ignore[arg-type]
    )
