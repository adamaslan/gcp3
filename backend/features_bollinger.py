"""Feature #11 — Bollinger Band Position.

Computes enriched BB state per ticker per timeframe:
  - Exact band values
  - position_pct (continuous 0–1 mapping, can exceed bounds)
  - band_width_pct (volatility proxy)
  - squeeze flag (band width at 6-month low = pre-breakout tell)

Data source: yfinance OHLCV (nightly for 1M+, Finnhub 5-min refresh for 1D/5D).
"""
import logging
from dataclasses import dataclass
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BollingerPosition:
    timeframe: str
    period: int
    stddev_mult: float
    upper_band: float
    middle_band: float
    lower_band: float
    current_price: float
    position: Literal["above_upper", "upper_half", "lower_half", "below_lower"]
    position_pct: float
    band_width_pct: float
    squeeze: bool


def compute_bollinger(
    closes: pd.Series,
    timeframe: str = "1D",
    period: int = 20,
    stddev_mult: float = 2.0,
) -> BollingerPosition | None:
    """Compute Bollinger Band features from a closing-price series.

    Args:
        closes: Time-ordered closing prices (oldest first).
        timeframe: One of 1D, 5D, 1M, 3M, 6M, 1Y.
        period: Rolling window (default 20).
        stddev_mult: Standard deviation multiplier (default 2).

    Returns:
        BollingerPosition or None if insufficient history.
    """
    if len(closes) < period + 1:
        logger.warning("bollinger: insufficient bars (need %d, got %d)", period + 1, len(closes))
        return None

    sma = closes.rolling(period).mean()
    rolling_std = closes.rolling(period).std()
    upper = sma + stddev_mult * rolling_std
    lower = sma - stddev_mult * rolling_std

    current = float(closes.iloc[-1])
    mid = float(sma.iloc[-1])
    up = float(upper.iloc[-1])
    lo = float(lower.iloc[-1])

    if mid == 0 or (up - lo) == 0:
        return None

    band_range = up - lo
    position_pct = (current - lo) / band_range
    band_width_pct = band_range / mid

    # Squeeze: current width within 5% of the 6-month (126 bar) minimum width
    width_series = (upper - lower) / sma
    six_month_min = float(width_series.tail(126).min())
    squeeze = band_width_pct <= six_month_min * 1.05

    if current > up:
        position = "above_upper"
    elif current >= mid:
        position = "upper_half"
    elif current >= lo:
        position = "lower_half"
    else:
        position = "below_lower"

    return BollingerPosition(
        timeframe=timeframe,
        period=period,
        stddev_mult=stddev_mult,
        upper_band=round(up, 4),
        middle_band=round(mid, 4),
        lower_band=round(lo, 4),
        current_price=round(current, 4),
        position=position,
        position_pct=round(position_pct, 4),
        band_width_pct=round(band_width_pct, 4),
        squeeze=squeeze,
    )


def format_bb_for_prompt(bb: BollingerPosition) -> str:
    """Compact Gemini prompt fragment for a single timeframe BB reading."""
    sq = "true" if bb.squeeze else "false"
    return f"<bb_{bb.timeframe.lower()}>pos={bb.position}({bb.position_pct:.2f}) bw={bb.band_width_pct:.1%} squeeze={sq}</bb_{bb.timeframe.lower()}>"


def validate_bollinger(bb: BollingerPosition) -> list[str]:
    """Return list of validation error strings; empty = valid."""
    errors: list[str] = []
    if not (bb.upper_band > bb.middle_band > bb.lower_band):
        errors.append(f"BB band ordering violated: upper={bb.upper_band} mid={bb.middle_band} lower={bb.lower_band}")
    if not (0 <= bb.band_width_pct <= 1):
        errors.append(f"band_width_pct={bb.band_width_pct} outside [0,1]")
    if not (-0.2 <= bb.position_pct <= 1.2):
        logger.warning("bb position_pct=%s outside normal range — flagged for review", bb.position_pct)
    return errors
