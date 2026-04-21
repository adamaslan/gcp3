"""Feature #13 — RSI + Divergence Detection.

Computes RSI(14) with Wilder's smoothing plus rule-based divergence detection:
  - Bullish/bearish regular and hidden divergence
  - divergence_strength score in [0,1]

Data source: Massive pre-computed RSI (free-tier) or yfinance OHLCV fallback.
"""
import logging
from dataclasses import dataclass
from typing import Literal

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RsiFeature:
    timeframe: str
    period: int
    current_rsi: float
    rsi_7d_trend: Literal["rising", "falling", "flat"]
    overbought: bool
    oversold: bool
    divergence: Literal[
        "bullish_regular",
        "bearish_regular",
        "bullish_hidden",
        "bearish_hidden",
        "none",
    ]
    divergence_strength: float
    bars_since_last_divergence: int
    midline_cross_days: int


def _wilders_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI — standard implementation."""
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("inf"))
    return 100 - (100 / (1 + rs))


def _find_swings(series: pd.Series, window: int = 3) -> tuple[list[int], list[int]]:
    """Return indices of local peaks and troughs via 3-bar swing detection."""
    peaks, troughs = [], []
    vals = series.values
    for i in range(window, len(vals) - window):
        segment = vals[i - window : i + window + 1]
        if vals[i] == max(segment):
            peaks.append(i)
        elif vals[i] == min(segment):
            troughs.append(i)
    return peaks, troughs


def _detect_divergence(
    closes: pd.Series,
    rsi: pd.Series,
    lookback: int = 30,
) -> tuple[str, float, int]:
    """Rule-based divergence detector. Returns (pattern, strength, bars_since)."""
    if len(closes) < lookback:
        return "none", 0.0, 999

    c = closes.tail(lookback).reset_index(drop=True)
    r = rsi.tail(lookback).reset_index(drop=True)

    price_peaks, price_troughs = _find_swings(c)
    rsi_peaks, rsi_troughs = _find_swings(r)

    best_div = "none"
    best_strength = 0.0

    # Bearish regular: price HH, RSI LH
    for i in range(1, len(price_peaks)):
        p1, p2 = price_peaks[i - 1], price_peaks[i]
        if c[p2] > c[p1]:
            matching_rsi = [j for j in rsi_peaks if abs(j - p2) <= 2]
            if matching_rsi:
                r2 = max(matching_rsi, key=lambda j: abs(j - p2))
                earlier_rsi = [j for j in rsi_peaks if abs(j - p1) <= 2]
                if earlier_rsi:
                    r1 = max(earlier_rsi, key=lambda j: abs(j - p1))
                    if r[r2] < r[r1]:
                        price_delta = abs(c[p2] - c[p1]) / max(c[p1], 1e-9)
                        rsi_delta = abs(r[r2] - r[r1]) / 100
                        strength = min(1.0, rsi_delta / max(price_delta, 1e-9) * 0.5)
                        if strength > best_strength:
                            best_div = "bearish_regular"
                            best_strength = strength

    # Bullish regular: price LL, RSI HL
    for i in range(1, len(price_troughs)):
        p1, p2 = price_troughs[i - 1], price_troughs[i]
        if c[p2] < c[p1]:
            matching_rsi = [j for j in rsi_troughs if abs(j - p2) <= 2]
            if matching_rsi:
                r2 = max(matching_rsi, key=lambda j: abs(j - p2))
                earlier_rsi = [j for j in rsi_troughs if abs(j - p1) <= 2]
                if earlier_rsi:
                    r1 = max(earlier_rsi, key=lambda j: abs(j - p1))
                    if r[r2] > r[r1]:
                        price_delta = abs(c[p2] - c[p1]) / max(c[p1], 1e-9)
                        rsi_delta = abs(r[r2] - r[r1]) / 100
                        strength = min(1.0, rsi_delta / max(price_delta, 1e-9) * 0.5)
                        if strength > best_strength:
                            best_div = "bullish_regular"
                            best_strength = strength

    bars_since = 0 if best_div != "none" else 999
    return best_div, round(best_strength, 3), bars_since  # type: ignore[return-value]


def compute_rsi(
    closes: pd.Series,
    timeframe: str = "1D",
    period: int = 14,
) -> RsiFeature | None:
    """Compute RSI with divergence detection.

    Args:
        closes: Time-ordered closing prices (oldest first).
        timeframe: Timeframe label.
        period: RSI period (default 14).

    Returns:
        RsiFeature or None if insufficient history.
    """
    if len(closes) < period + 20:
        logger.warning("rsi: insufficient bars (need %d, got %d)", period + 20, len(closes))
        return None

    rsi = _wilders_rsi(closes, period)
    current = float(rsi.iloc[-1])

    # 7-day trend
    if len(rsi) >= 7:
        delta = float(rsi.iloc[-1]) - float(rsi.iloc[-7])
        trend: str = "rising" if delta > 1 else "falling" if delta < -1 else "flat"
    else:
        trend = "flat"

    # Midline cross (50)
    midline_cross_days = 0
    for i in range(len(rsi) - 2, -1, -1):
        v1, v2 = float(rsi.iloc[i]), float(rsi.iloc[i + 1])
        if (v1 < 50 and v2 >= 50) or (v1 > 50 and v2 <= 50):
            midline_cross_days = len(rsi) - 1 - i
            break

    divergence, div_strength, bars_since = _detect_divergence(closes, rsi)

    return RsiFeature(
        timeframe=timeframe,
        period=period,
        current_rsi=round(current, 2),
        rsi_7d_trend=trend,  # type: ignore[arg-type]
        overbought=current > 70,
        oversold=current < 30,
        divergence=divergence,  # type: ignore[arg-type]
        divergence_strength=div_strength,
        bars_since_last_divergence=bars_since,
        midline_cross_days=midline_cross_days,
    )


def format_rsi_for_prompt(rsi: RsiFeature) -> str:
    div_str = (
        f" divergence={rsi.divergence} strength={rsi.divergence_strength}"
        if rsi.divergence != "none"
        else " divergence=none"
    )
    return f"<rsi_{rsi.timeframe.lower()}>val={rsi.current_rsi:.0f} trend={rsi.rsi_7d_trend}{div_str}</rsi_{rsi.timeframe.lower()}>"


def validate_rsi(rsi: RsiFeature) -> list[str]:
    errors: list[str] = []
    if not (0 <= rsi.current_rsi <= 100):
        errors.append(f"current_rsi={rsi.current_rsi} outside [0,100]")
    if not (0 <= rsi.divergence_strength <= 1):
        errors.append(f"divergence_strength={rsi.divergence_strength} outside [0,1]")
    return errors
