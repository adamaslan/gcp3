"""Feature #19 — Breadth Oscillators.

Market-wide breadth indicators:
  - % above 50d/200d MA
  - McClellan Oscillator & Summation Index
  - Zweig Breadth Thrust
  - New highs vs new lows
  - Divergence flag vs SPY

Data source: BigQuery SQL on mart.etf_ohlcv_with_ma (nightly compute).
This module computes from a universe DataFrame for in-process testing/backfill.
"""
import logging
from dataclasses import dataclass
from typing import Literal

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BreadthOscillators:
    as_of_date: str
    universe: str
    pct_above_50d_ma: float
    pct_above_200d_ma: float
    breadth_ema_5d: float
    breadth_ema_20d: float
    breadth_momentum_5d: float
    breadth_momentum_20d: float
    zweig_breadth_thrust: bool
    zweig_days_since_trigger: int
    mcclellan_oscillator: float
    mcclellan_summation: float
    new_highs_vs_new_lows: int
    divergence_flag: Literal[
        "bullish_breadth_divergence",
        "bearish_breadth_divergence",
        "confirming",
        "neutral",
    ]


def compute_breadth(
    daily_universe: pd.DataFrame,
    as_of_date: str,
    universe: str = "sp500",
    spy_closes: pd.Series | None = None,
) -> BreadthOscillators | None:
    """Compute breadth oscillators from a universe of daily OHLCV.

    Args:
        daily_universe: DataFrame with columns: ticker, date, close, ma_50, ma_200,
                        advancers (bool), decliners (bool), high_52w, low_52w.
        as_of_date: ISO date string.
        universe: Universe label ('sp500', 'nasdaq100', 'r2000').
        spy_closes: Optional SPY closing series for divergence detection.

    Returns:
        BreadthOscillators or None if insufficient data.
    """
    if len(daily_universe) < 30:
        logger.warning("breadth: insufficient universe data")
        return None

    today = daily_universe[daily_universe["date"] == as_of_date]
    if today.empty:
        logger.warning("breadth: no universe data for %s", as_of_date)
        return None

    total = len(today)
    pct_above_50 = float((today["close"] > today["ma_50"]).sum() / total)
    pct_above_200 = float((today["close"] > today["ma_200"]).sum() / total)

    # Historical breadth for EMAs (by date)
    breadth_by_date = (
        daily_universe.groupby("date")
        .apply(lambda df: (df["close"] > df["ma_50"]).sum() / len(df))
        .sort_index()
    )
    ema_5 = float(breadth_by_date.ewm(span=5, adjust=False).mean().iloc[-1])
    ema_20 = float(breadth_by_date.ewm(span=20, adjust=False).mean().iloc[-1])
    mom_5 = float(breadth_by_date.ewm(span=5, adjust=False).mean().diff().iloc[-1])
    mom_20 = float(breadth_by_date.ewm(span=20, adjust=False).mean().diff().iloc[-1])

    # Advances / declines for McClellan
    adv_dec_by_date = daily_universe.groupby("date").apply(
        lambda df: (df["advancers"].sum() - df["decliners"].sum()) / len(df)
    ).sort_index()

    mcclellan = float(
        adv_dec_by_date.ewm(span=19, adjust=False).mean().iloc[-1]
        - adv_dec_by_date.ewm(span=39, adjust=False).mean().iloc[-1]
    )
    mcclellan_summation = float(
        (adv_dec_by_date.ewm(span=19, adjust=False).mean()
         - adv_dec_by_date.ewm(span=39, adjust=False).mean()).cumsum().iloc[-1]
    )

    # New highs vs new lows
    nh = int((today["close"] >= today["high_52w"]).sum())
    nl = int((today["close"] <= today["low_52w"]).sum())

    # Zweig Breadth Thrust: 10d EMA of adv-ratio > 0.615 after being < 0.40
    adv_ratio = daily_universe.groupby("date").apply(
        lambda df: df["advancers"].sum() / len(df)
    ).sort_index()
    adv_ema_10 = adv_ratio.ewm(span=10, adjust=False).mean()
    zweig = False
    zweig_days = 999
    for i in range(len(adv_ema_10) - 1, max(0, len(adv_ema_10) - 30), -1):
        if adv_ema_10.iloc[i] > 0.615:
            # Check if any prior reading was < 0.40 within 10 days
            window = adv_ema_10.iloc[max(0, i - 10) : i]
            if (window < 0.40).any():
                zweig = True
                zweig_days = len(adv_ema_10) - 1 - i
                break

    # Divergence vs SPY
    divergence_flag: str = "neutral"
    if spy_closes is not None and len(spy_closes) >= 5:
        spy_5d = float(spy_closes.iloc[-1] - spy_closes.iloc[-5]) / float(spy_closes.iloc[-5])
        breadth_5d = ema_5 - float(breadth_by_date.ewm(span=5, adjust=False).mean().iloc[-5]) if len(breadth_by_date) >= 5 else 0.0
        if spy_5d < 0 and breadth_5d > 0.01:
            divergence_flag = "bullish_breadth_divergence"
        elif spy_5d > 0 and breadth_5d < -0.01:
            divergence_flag = "bearish_breadth_divergence"
        elif (spy_5d > 0) == (breadth_5d > 0):
            divergence_flag = "confirming"

    return BreadthOscillators(
        as_of_date=as_of_date,
        universe=universe,
        pct_above_50d_ma=round(pct_above_50, 3),
        pct_above_200d_ma=round(pct_above_200, 3),
        breadth_ema_5d=round(ema_5, 3),
        breadth_ema_20d=round(ema_20, 3),
        breadth_momentum_5d=round(mom_5, 4),
        breadth_momentum_20d=round(mom_20, 4),
        zweig_breadth_thrust=zweig,
        zweig_days_since_trigger=zweig_days,
        mcclellan_oscillator=round(mcclellan, 2),
        mcclellan_summation=round(mcclellan_summation, 2),
        new_highs_vs_new_lows=nh - nl,
        divergence_flag=divergence_flag,  # type: ignore[arg-type]
    )


def format_breadth_for_prompt(b: BreadthOscillators) -> str:
    return (
        f"<breadth>\n"
        f"  pct_50ma={b.pct_above_50d_ma:.0%} ema_5d={b.breadth_ema_5d:.0%} ema_20d={b.breadth_ema_20d:.0%}\n"
        f"  momentum_5d={b.breadth_momentum_5d:+.2%}/day "
        f"zweig_thrust={str(b.zweig_breadth_thrust).lower()}\n"
        f"  mcclellan={b.mcclellan_oscillator:.0f} summation={b.mcclellan_summation:.0f} "
        f"nh_nl={b.new_highs_vs_new_lows:+d}\n"
        f"  divergence={b.divergence_flag}\n"
        f"</breadth>"
    )
