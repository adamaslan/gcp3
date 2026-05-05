"""Feature Store Service Layer.

Single entry point: get_features(ticker, as_of_date, feature_names).
Caches to Firestore with TTLs. Returns feature_unavailable sentinel on errors.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from firestore import get_cache, set_cache

logger = logging.getLogger(__name__)

FEATURE_UNAVAILABLE = "feature_unavailable"

# TTLs in seconds per feature group
_TTL: dict[str, int] = {
    "bollinger": 300,        # intraday 5-min refresh
    "volume": 300,
    "rsi": 300,
    "macd": 300,
    "correlation": 86_400,
    "regime": 86_400,
    "alignment": 14_400,
    "sector_relative": 86_400,
    "breadth": 3_600,
    "options_sentiment": 86_400,
    "vix_term": 3_600,
    "cross_asset": 3_600,
    "earnings_surprise": 86_400,
}

# yfinance history period per signal timeframe for OHLCV-based features
_TF_HISTORY_PERIOD: dict[str, str] = {
    "1D": "3mo",
    "5D": "3mo",
    "1M": "6mo",
    "3M": "1y",
    "6M": "2y",
    "1Y": "5y",
}

_FEATURE_MODULES: dict[str, str] = {
    "bollinger": "features_bollinger",
    "volume": "features_volume",
    "rsi": "features_rsi",
    "macd": "features_macd",
    "correlation": "features_correlation",
    "regime": "features_regime",
    "alignment": "features_alignment",
    "sector_relative": "features_sector_relative",
    "breadth": "features_breadth",
    "options_sentiment": "features_options_sentiment",
    "vix_term": "features_vix_term",
    "cross_asset": "features_cross_asset",
    "earnings_surprise": "features_earnings_surprise",
}

DEFAULT_REGIME_INPUTS = {
    "vix_spot": 18.0,
    "vix_3m": 19.5,
    "yield_10y_2y_spread": 0.5,
    "spy_return_5d": 0.0,
    "breadth_pct": 0.55,
    "put_call_ratio": 0.85,
}


async def _compute_feature(
    feature_name: str, ticker: str, as_of: date, timeframe: str = "1D"
) -> Any:
    """Dispatch to the appropriate feature module."""
    try:
        yf_period = _TF_HISTORY_PERIOD.get(timeframe, "3mo")

        if feature_name == "bollinger":
            import yfinance as yf
            from features_bollinger import compute_bollinger
            ticker_obj = yf.Ticker(ticker)
            hist = await asyncio.to_thread(ticker_obj.history, period=yf_period)
            closes = hist["Close"].dropna()
            result = compute_bollinger(closes, timeframe=timeframe)
            return result.__dict__ if result else FEATURE_UNAVAILABLE

        if feature_name == "volume":
            import yfinance as yf
            from features_volume import compute_volume_zscore
            ticker_obj = yf.Ticker(ticker)
            hist = await asyncio.to_thread(ticker_obj.history, period=yf_period)
            hist = hist.rename(columns={c: c.lower() for c in hist.columns})
            result = compute_volume_zscore(hist[["volume", "close"]].dropna())
            return result.__dict__ if result else FEATURE_UNAVAILABLE

        if feature_name == "rsi":
            import yfinance as yf
            from features_rsi import compute_rsi
            ticker_obj = yf.Ticker(ticker)
            hist = await asyncio.to_thread(ticker_obj.history, period=yf_period)
            result = compute_rsi(hist["Close"].dropna())
            return result.__dict__ if result else FEATURE_UNAVAILABLE

        if feature_name == "macd":
            import yfinance as yf
            from features_macd import compute_macd
            ticker_obj = yf.Ticker(ticker)
            hist = await asyncio.to_thread(ticker_obj.history, period=yf_period)
            result = compute_macd(hist["Close"].dropna())
            return result.__dict__ if result else FEATURE_UNAVAILABLE

        if feature_name == "alignment":
            from features_alignment import compute_alignment
            signals = {"1D": "hold", "5D": "hold", "1M": "hold", "3M": "hold", "6M": "hold", "1Y": "hold"}
            confidences = {tf: 0.5 for tf in signals}
            result = compute_alignment(ticker, signals, confidences)
            return result.__dict__

        if feature_name == "regime":
            from features_regime import compute_regime
            result = compute_regime(
                DEFAULT_REGIME_INPUTS["vix_spot"],
                DEFAULT_REGIME_INPUTS["vix_3m"],
                DEFAULT_REGIME_INPUTS["yield_10y_2y_spread"],
                DEFAULT_REGIME_INPUTS["spy_return_5d"],
                DEFAULT_REGIME_INPUTS["breadth_pct"],
                DEFAULT_REGIME_INPUTS["put_call_ratio"],
                as_of.isoformat(),
            )
            return result.__dict__

        if feature_name == "correlation":
            return {
                "ticker": ticker,
                "avg_market_corr": 0.0,
                "avg_sector_corr": 0.0,
                "idiosyncratic_score": 0.5,
                "regime_flag": "not_computed",
            }

        if feature_name == "sector_relative":
            return {
                "ticker": ticker,
                "is_sector_leader": False,
                "is_sector_laggard": False,
                "momentum_shift": "stable",
                "per_tf_vs_market": {},
            }

        if feature_name == "breadth":
            return {"status": "not_computed", "score": 0.5}

        if feature_name == "options_sentiment":
            from features_options_sentiment import fetch_options_sentiment
            result = await fetch_options_sentiment()
            return result.__dict__

        if feature_name == "vix_term":
            from features_vix_term import fetch_vix_term_structure
            result = await fetch_vix_term_structure()
            return result.__dict__

        if feature_name == "cross_asset":
            from features_cross_asset import fetch_cross_asset_signals
            result = await fetch_cross_asset_signals()
            return result.__dict__

        if feature_name == "earnings_surprise":
            from features_earnings_surprise import fetch_earnings_surprise
            result = await fetch_earnings_surprise(ticker)
            return result.__dict__

        logger.warning("feature_store: unknown feature_name=%s", feature_name)
        return FEATURE_UNAVAILABLE

    except Exception as e:
        logger.error("feature_compute_failed feature=%s ticker=%s error=%s", feature_name, ticker, e)
        return FEATURE_UNAVAILABLE


async def get_features(
    ticker: str,
    as_of_date: date,
    feature_names: list[str],
    timeframe: str = "1D",
) -> dict[str, Any]:
    """Fetch features for a ticker, using Firestore cache where possible.

    Args:
        ticker: Stock symbol.
        as_of_date: Date context for cache keying.
        feature_names: List of feature group names to fetch.
        timeframe: Signal timeframe (1D/5D/1M/3M/6M/1Y). Controls history window
            for OHLCV-based features so indicators match the analysis period.

    Returns:
        Dict mapping feature_name -> feature data or FEATURE_UNAVAILABLE sentinel.
    """
    results: dict[str, Any] = {}
    missing: list[str] = []

    # Check cache for each feature
    for name in feature_names:
        cache_key = f"feature:{name}:{ticker}:{timeframe}:{as_of_date.isoformat()}"
        try:
            cached = get_cache(cache_key)
            if cached is not None:
                logger.debug("feature_cache_hit feature=%s ticker=%s tf=%s", name, ticker, timeframe)
                results[name] = cached
                continue
        except Exception:
            pass
        missing.append(name)

    if not missing:
        return results

    # Compute missing features concurrently
    computed = await asyncio.gather(
        *[_compute_feature(name, ticker, as_of_date, timeframe) for name in missing],
        return_exceptions=True,
    )

    for name, value in zip(missing, computed):
        if isinstance(value, Exception):
            logger.error("feature_gather_exception feature=%s ticker=%s tf=%s error=%s", name, ticker, timeframe, value)
            results[name] = FEATURE_UNAVAILABLE
        else:
            results[name] = value
            if value != FEATURE_UNAVAILABLE:
                ttl = _TTL.get(name, 3_600)
                cache_key = f"feature:{name}:{ticker}:{timeframe}:{as_of_date.isoformat()}"
                try:
                    set_cache(cache_key, value, ttl_seconds=ttl)
                except Exception as e:
                    logger.warning("feature_cache_write_failed feature=%s tf=%s error=%s", name, timeframe, e)

    return results
