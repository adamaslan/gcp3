"""Daily OHLCV history for analytics: Alpaca first, yfinance only on local runs.

Returns yfinance-shaped DataFrames (Open/High/Low/Close/Volume, DatetimeIndex) so callers
that previously did ``yf.Ticker(sym).history(...)`` swap in without other changes. An empty
frame means "no data from any permitted source"; callers already treat empty as unavailable.

Not for the stored ETF history (etf_store): that series is dividend-adjusted by yfinance and
Alpaca bars are split-adjusted only, so mixing them would put a step in the series.
"""
import logging
import re
from datetime import date, timedelta

import pandas as pd

import alpaca_md

logger = logging.getLogger(__name__)

BUFFER_DAYS = 7  # weekends and holidays
CALENDAR_DAYS_PER_UNIT = {"d": 1, "wk": 7, "mo": 31, "y": 366}
PERIOD_PATTERN = re.compile(r"^(\d+)(d|wk|mo|y)$")
MAX_PERIOD_DAYS = 3650


def period_to_days(period: str) -> int:
    """'2d' -> 9, '3mo' -> 100, '2y' -> 739, 'ytd' -> days since Jan 1, 'max' -> ten years."""
    if period == "ytd":
        return (date.today() - date(date.today().year, 1, 1)).days + BUFFER_DAYS
    if period == "max":
        return MAX_PERIOD_DAYS
    match = PERIOD_PATTERN.match(period)
    if not match:
        raise ValueError(f"unsupported period {period!r}")
    count, unit = int(match.group(1)), match.group(2)
    return min(count * CALENDAR_DAYS_PER_UNIT[unit] + BUFFER_DAYS, MAX_PERIOD_DAYS)


def daily_history(symbol: str, period: str = "3mo") -> pd.DataFrame:
    """Blocking fetch of daily bars for one symbol; safe to run in a thread pool."""
    return daily_history_days(symbol, period_to_days(period), yf_period=period)


def daily_history_days(symbol: str, days: int, *, yf_period: str | None = None) -> pd.DataFrame:
    """Daily bars covering the last ``days`` calendar days."""
    if alpaca_md.is_configured():
        try:
            frame = alpaca_md.daily_bars_frames([symbol], days).get(symbol)
            if frame is not None and not frame.empty:
                return frame
            alpaca_md.warn_fallback("daily history", [symbol], "no Alpaca bars")
        except alpaca_md.AlpacaError as exc:
            alpaca_md.warn_fallback("daily history", [symbol], exc)
    else:
        logger.warning("history_client: Alpaca not configured; %s falls back", symbol)
    if alpaca_md.on_datacenter_host():
        logger.error("history_client: yfinance skipped on a datacenter host; no history for %s", symbol)
        return pd.DataFrame()
    import yfinance as yf

    if yf_period:
        return yf.Ticker(symbol).history(period=yf_period)
    start = date.today() - timedelta(days=days)
    return yf.Ticker(symbol).history(start=start, end=date.today() + timedelta(days=1), interval="1d")
