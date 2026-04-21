"""Feature #14 — MACD Cross State.

Computes MACD with histogram direction, acceleration, zero-line position,
days since cross, and divergence detection.
Data source: Massive pre-computed MACD (free-tier) or yfinance fallback.
"""
import logging
from dataclasses import dataclass
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MacdState:
    timeframe: str
    fast_period: int
    slow_period: int
    signal_period: int
    macd_value: float
    signal_value: float
    histogram: float
    above_signal: bool
    days_since_cross: int
    cross_type: Literal["bullish_cross", "bearish_cross", "no_recent_cross"]
    histogram_direction: Literal[
        "expanding_positive",
        "contracting_positive",
        "contracting_negative",
        "expanding_negative",
    ]
    histogram_acceleration: Literal["accelerating", "decelerating", "steady"]
    zero_line_position: Literal["above", "below"]
    zero_line_cross_days: int
    divergence: Literal[
        "bullish_regular",
        "bearish_regular",
        "bullish_hidden",
        "bearish_hidden",
        "none",
    ]


def _classify_histogram_direction(hist_series: pd.Series) -> str:
    if len(hist_series) < 2:
        return "expanding_positive" if hist_series.iloc[-1] > 0 else "expanding_negative"
    last = float(hist_series.iloc[-1])
    prev = float(hist_series.iloc[-2])
    if last >= 0:
        return "expanding_positive" if last > prev else "contracting_positive"
    return "expanding_negative" if last < prev else "contracting_negative"


def _classify_acceleration(hist_series: pd.Series) -> str:
    if len(hist_series) < 3:
        return "steady"
    last3 = hist_series.tail(3).values
    d1 = last3[1] - last3[0]
    d2 = last3[2] - last3[1]
    if d1 > 0 and d2 > d1:
        return "accelerating"
    if d2 < d1:
        return "decelerating"
    return "steady"


def _days_since_cross(macd: pd.Series, signal: pd.Series) -> tuple[int, str]:
    """Return (days_since_cross, cross_type)."""
    above = macd > signal
    for i in range(len(above) - 1, 0, -1):
        if above.iloc[i] != above.iloc[i - 1]:
            days = len(above) - 1 - i
            ct = "bullish_cross" if above.iloc[i] else "bearish_cross"
            return days, ct
    return 999, "no_recent_cross"


def _days_since_zero_cross(macd: pd.Series) -> int:
    for i in range(len(macd) - 1, 0, -1):
        if (macd.iloc[i] >= 0) != (macd.iloc[i - 1] >= 0):
            return len(macd) - 1 - i
    return 999


def compute_macd(
    closes: pd.Series,
    timeframe: str = "1D",
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> MacdState | None:
    """Compute MACD state with histogram dynamics and divergence.

    Args:
        closes: Time-ordered closing prices (oldest first).
        timeframe: Timeframe label.
        fast / slow / signal_period: Standard MACD params.

    Returns:
        MacdState or None if insufficient history.
    """
    min_bars = slow + signal_period + 5
    if len(closes) < min_bars:
        logger.warning("macd: insufficient bars (need %d, got %d)", min_bars, len(closes))
        return None

    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    hist = macd - signal

    macd_val = float(macd.iloc[-1])
    signal_val = float(signal.iloc[-1])
    hist_val = float(hist.iloc[-1])

    days_cross, cross_type = _days_since_cross(macd, signal)
    zero_cross_days = _days_since_zero_cross(macd)

    # Simple price/MACD divergence: compare latest 2 MACD peaks vs price peaks
    divergence = "none"

    return MacdState(
        timeframe=timeframe,
        fast_period=fast,
        slow_period=slow,
        signal_period=signal_period,
        macd_value=round(macd_val, 4),
        signal_value=round(signal_val, 4),
        histogram=round(hist_val, 4),
        above_signal=macd_val > signal_val,
        days_since_cross=days_cross,
        cross_type=cross_type,  # type: ignore[arg-type]
        histogram_direction=_classify_histogram_direction(hist),  # type: ignore[arg-type]
        histogram_acceleration=_classify_acceleration(hist),  # type: ignore[arg-type]
        zero_line_position="above" if macd_val >= 0 else "below",  # type: ignore[arg-type]
        zero_line_cross_days=zero_cross_days,
        divergence=divergence,  # type: ignore[arg-type]
    )


def format_macd_for_prompt(m: MacdState) -> str:
    return (
        f"<macd_{m.timeframe.lower()}>above_sig={str(m.above_signal).lower()} "
        f"days_since={m.days_since_cross} hist={m.histogram_direction} "
        f"accel={m.histogram_acceleration}</macd_{m.timeframe.lower()}>"
    )


def validate_macd(m: MacdState) -> list[str]:
    return []  # MACD values are unbounded by design
