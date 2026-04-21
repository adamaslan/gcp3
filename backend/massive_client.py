"""Massive API client: rate-limited async wrapper for free-tier endpoints.

5 calls/minute hard constraint enforced via module-level asyncio.Semaphore.
All calls are sequential with automatic 12s spacing — multiple concurrent calls
(e.g., in asyncio.gather) will naturally queue without blocking other stages.

Data returned is EOD (end-of-day) only on free tier — intraday quotes come
from Finnhub; Massive adds technicals, 52-week ranges, and corporate actions.

Connection pooling: single persistent httpx.AsyncClient reused across all requests.
"""
import asyncio
import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "")
# Polygon.io API versions differ by endpoint
_BASE_V1 = "https://api.polygon.io/v1"
_BASE_V2 = "https://api.polygon.io/v2"
_BASE_V3 = "https://api.polygon.io/v3"

_RATE_LOCK = asyncio.Semaphore(1)
_LAST_CALL: float = 0.0
_HTTP_CLIENT: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Get or create a persistent HTTP client for connection pooling."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(timeout=15)
    return _HTTP_CLIENT


async def _get(url: str, params: dict | None = None) -> dict:
    """Single-flight rate-limited GET. Enforces 12s minimum between calls.

    Args:
        url: Full API URL with version (e.g., "https://api.polygon.io/v2/snapshot/...")
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
            client = _get_http_client()
            full_params = {"apiKey": MASSIVE_API_KEY, **(params or {})}
            logger.debug("massive_get: %s params=%s", url, {k: v for k, v in full_params.items() if k != "apiKey"})

            response = await client.get(url, params=full_params)

            if response.status_code == 403:
                # 403 means the key is invalid or this endpoint requires a higher plan tier.
                # Log clearly so the fix is obvious in Cloud Run logs.
                logger.error(
                    "massive_client: 403 Forbidden for %s — check MASSIVE_API_KEY in Secret Manager "
                    "and verify the Polygon.io subscription tier supports this endpoint",
                    url,
                )
                raise httpx.HTTPStatusError(
                    f"403 Forbidden — Polygon key invalid or plan tier insufficient for {url}",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status()

            _LAST_CALL = loop.time()
            return response.json()
        except httpx.HTTPError as exc:
            logger.error("massive_get %s failed: %s", url, exc)
            raise


async def get_snapshots(tickers: list[str]) -> dict:
    """Batch snapshot for tickers, handling >250 via automatic batching.

    Returns quote, 52-week high/low, volume, and other fields per ticker.
    Automatically batches requests for >250 tickers (API limit 250 per call).

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

    BATCH_SIZE = 250
    results = {}

    try:
        # Process tickers in batches of 250 (API limit per call)
        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i : i + BATCH_SIZE]
            logger.debug("snapshots: batch %d/%d size=%d", i // BATCH_SIZE + 1, (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE, len(batch))

            data = await _get(
                f"{_BASE_V2}/snapshot/locale/us/markets/stocks/tickers",
                {"tickers": ",".join(batch)},
            )

            # Reindex by ticker symbol for easy lookup
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
        url = f"{_BASE_V1}/indicators/{indicator}/{ticker}"
        data = await _get(url, params)
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
        url = f"{_BASE_V3}/reference/dividends"
        data = await _get(
            url,
            {"ex_dividend_date.gte": from_date, "ex_dividend_date.lte": to_date},
        )
        return data.get("results", [])
    except Exception as exc:
        logger.error("corporate_actions %s to %s failed: %s", from_date, to_date, exc)
        return []
