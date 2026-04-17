"""Massive API client: rate-limited async wrapper for free-tier endpoints.

5 calls/minute hard constraint enforced via module-level asyncio.Semaphore.
All calls are sequential with automatic 12s spacing — multiple concurrent calls
(e.g., in asyncio.gather) will naturally queue without blocking other stages.

Data returned is EOD (end-of-day) only on free tier — intraday quotes come
from Finnhub; Massive adds technicals, 52-week ranges, and corporate actions.
"""
import asyncio
import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "")
_BASE = "https://api.polygon.io/v2"  # Polygon.io standard endpoint — Massive is Polygon-compatible
_RATE_LOCK = asyncio.Semaphore(1)
_LAST_CALL: float = 0.0


async def _get(path: str, params: dict | None = None) -> dict:
    """Single-flight rate-limited GET. Enforces 12s minimum between calls.

    Args:
        path: API path (e.g., "/snapshot/locale/us/markets/stocks/tickers")
        params: Query parameters (excluding apiKey, which is auto-added)

    Returns:
        Parsed JSON response dict

    Raises:
        httpx.HTTPError on non-2xx status
        KeyError if MASSIVE_API_KEY not set
    """
    global _LAST_CALL

    if not MASSIVE_API_KEY:
        raise KeyError("MASSIVE_API_KEY environment variable not set")

    async with _RATE_LOCK:
        # Calculate wait time to enforce 12s minimum between calls
        loop = asyncio.get_running_loop()
        now = loop.time()
        wait = 12.0 - (now - _LAST_CALL)
        if wait > 0:
            logger.debug("rate_limit: sleeping %.1fs", wait)
            await asyncio.sleep(wait)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                url = f"{_BASE}{path}"
                full_params = {"apiKey": MASSIVE_API_KEY, **(params or {})}
                logger.debug("massive_get: %s params=%s", path, {k: v for k, v in full_params.items() if k != "apiKey"})

                response = await client.get(url, params=full_params)
                response.raise_for_status()

                _LAST_CALL = loop.time()
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("massive_get %s failed: %s", path, exc)
            raise


async def get_snapshots(tickers: list[str]) -> dict:
    """Batch snapshot for up to 250 tickers in one call.

    Returns quote, 52-week high/low, volume, and other fields per ticker.

    Args:
        tickers: List of ticker symbols (e.g., ["SPY", "QQQ", "AAPL"])

    Returns:
        Dict mapping ticker -> snapshot dict with keys:
        - updated: timestamp
        - price (c): current price
        - change (d): price change
        - change_pct (dp): percent change
        - high_52week: 52-week high
        - low_52week: 52-week low
        - volume: trading volume
        ... and more fields

    Example:
        >>> snapshots = await get_snapshots(["SPY", "QQQ"])
        >>> spy_price = snapshots["SPY"]["c"]
    """
    if not tickers:
        return {}

    try:
        data = await _get(
            "/snapshot/locale/us/markets/stocks/tickers",
            {"tickers": ",".join(tickers[:250])},  # API limit 250 per call
        )

        # Reindex by ticker symbol for easy lookup
        results = {}
        for ticker_data in data.get("results", []):
            ticker = ticker_data.get("ticker", "")
            if ticker:
                results[ticker] = ticker_data

        missing = set(tickers) - set(results.keys())
        if missing:
            logger.warning("snapshots missing from Massive: %s", missing)

        return results
    except Exception as exc:
        logger.error("snapshots %s failed: %s", tickers, exc)
        return {}


async def get_technical_indicators(ticker: str, indicator: str = "rsi", window: int = 14) -> dict | None:
    """Get technical indicator for a single ticker.

    Available indicators: rsi, macd, ema, sma, etc.

    Args:
        ticker: Single ticker symbol (e.g., "AAPL")
        indicator: Indicator name (default: "rsi")
        window: Period window (default: 14 for RSI)

    Returns:
        Dict with indicator data or None if failed

    Example:
        >>> rsi = await get_technical_indicators("AAPL", "rsi", 14)
        >>> if rsi:
        ...     print(rsi.get("value"))
    """
    try:
        params = {"window": window, "series_type": "close"}
        data = await _get(f"/indicators/{indicator}/{ticker}", params)
        return data.get("results", {})
    except Exception as exc:
        logger.error("technical_indicators %s %s failed: %s", ticker, indicator, exc)
        return None


async def get_corporate_actions(from_date: str, to_date: str) -> list[dict]:
    """Get corporate actions (dividends, splits, earnings) in date range.

    Args:
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)

    Returns:
        List of corporate action dicts with fields:
        - ex_dividend_date
        - amount (for dividends)
        - ticker
        ... and more

    Example:
        >>> actions = await get_corporate_actions("2026-04-17", "2026-05-17")
        >>> for action in actions:
        ...     print(f"{action['ticker']}: {action['ex_dividend_date']}")
    """
    try:
        data = await _get(
            "/reference/dividends",
            {"ex_dividend_date.gte": from_date, "ex_dividend_date.lte": to_date},
        )
        return data.get("results", [])
    except Exception as exc:
        logger.error("corporate_actions %s to %s failed: %s", from_date, to_date, exc)
        return []
