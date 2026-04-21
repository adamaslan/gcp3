"""Feature Refresh Orchestration.

Cloud Scheduler -> Cloud Run job entry point.
Dispatches intraday (#11 1D/5D, #12 1D) every 5min during market hours.
EOD batch for all others. Earnings-season hourly refresh for #23.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

# Intraday features refreshed every 5 minutes during market hours
INTRADAY_FEATURES = ["bollinger", "volume", "rsi", "macd"]
# End-of-day batch features
EOD_FEATURES = [
    "correlation", "regime", "alignment", "sector_relative",
    "breadth", "options_sentiment", "cross_asset",
]
# Hourly during earnings season
EARNINGS_FEATURES = ["earnings_surprise"]

MARKET_OPEN_HOUR_ET = 9
MARKET_CLOSE_HOUR_ET = 16

# Representative ticker universe for intraday refresh
from screener import WATCHLIST as INTRADAY_UNIVERSE


def _is_market_hours() -> bool:
    """Check if current UTC time is within US market hours (ET 9:30–16:00 approx)."""
    now_utc = datetime.now(timezone.utc)
    # UTC offset for ET: -4 (EDT) or -5 (EST); approximate with -4
    hour_et = (now_utc.hour - 4) % 24
    return MARKET_OPEN_HOUR_ET <= hour_et < MARKET_CLOSE_HOUR_ET


async def refresh_intraday(tickers: list[str] | None = None) -> dict:
    """Refresh intraday features (bollinger 1D/5D, volume 1D) for all tickers."""
    universe = tickers or INTRADAY_UNIVERSE
    logger.info("feature_refresh intraday start tickers=%d", len(universe))
    from feature_store import get_features
    results = await asyncio.gather(
        *[get_features(t, date.today(), INTRADAY_FEATURES) for t in universe],
        return_exceptions=True,
    )
    errors = sum(1 for r in results if isinstance(r, Exception))
    logger.info("feature_refresh intraday done tickers=%d errors=%d", len(universe), errors)
    return {"tickers": len(universe), "errors": errors, "type": "intraday"}


async def refresh_eod(tickers: list[str] | None = None) -> dict:
    """Refresh end-of-day batch features for all tickers."""
    universe = tickers or INTRADAY_UNIVERSE
    logger.info("feature_refresh eod start tickers=%d", len(universe))
    from feature_store import get_features
    results = await asyncio.gather(
        *[get_features(t, date.today(), EOD_FEATURES) for t in universe],
        return_exceptions=True,
    )
    errors = sum(1 for r in results if isinstance(r, Exception))
    logger.info("feature_refresh eod done tickers=%d errors=%d", len(universe), errors)
    return {"tickers": len(universe), "errors": errors, "type": "eod"}


async def refresh_earnings(tickers: list[str] | None = None) -> dict:
    """Refresh earnings surprise features (hourly during earnings season)."""
    universe = tickers or INTRADAY_UNIVERSE
    logger.info("feature_refresh earnings start tickers=%d", len(universe))
    from feature_store import get_features
    results = await asyncio.gather(
        *[get_features(t, date.today(), EARNINGS_FEATURES) for t in universe],
        return_exceptions=True,
    )
    errors = sum(1 for r in results if isinstance(r, Exception))
    logger.info("feature_refresh earnings done tickers=%d errors=%d", len(universe), errors)
    return {"tickers": len(universe), "errors": errors, "type": "earnings"}


async def run_refresh_job(job_type: str = "auto") -> dict:
    """Main Cloud Run entry point dispatched by Cloud Scheduler.

    Args:
        job_type: "intraday" | "eod" | "earnings" | "auto" (auto-detects by time).

    Returns:
        Summary dict.
    """
    if job_type == "intraday" or (job_type == "auto" and _is_market_hours()):
        return await refresh_intraday()
    if job_type == "earnings":
        return await refresh_earnings()
    return await refresh_eod()


if __name__ == "__main__":
    job = os.getenv("REFRESH_JOB_TYPE", "auto")
    result = asyncio.run(run_refresh_job(job))
    print(result)
