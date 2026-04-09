"""Unified market data client.

Resolution chain for any quote request:
  1. Firestore cache  — instant, free, shared across instances
  2. Finnhub          — real-time intraday (primary live source)
                        rate-limited: semaphore(25) + 50ms stagger + 429 retry
  3. yfinance         — free fallback, no API key, no quota
                        rate-limited: semaphore(4) + randomized 0.5–1.5s delay
                        custom User-Agent to avoid bot detection
                        runs in a thread pool (sync library)

Analytics enrichment (multi-period returns) via Alpha Vantage:
  - ANALYTICS_FIXED_WINDOW batches 5 symbols per call (free tier max)
  - 50 ETFs → 10 AV calls instead of 50
  - Only runs when AV quota allows; never blocks quote delivery
  - Daily call counter resets at midnight UTC

yfinance rate limits (IP-based):
  ~100–200 req/min, ~2,000 req/hr. Rapid bursts trigger 429 faster than
  sustained load. Semaphore(4) + 0.5–1.5s randomized delay keeps us at
  ~40–80 req/min, well under limits. Bulk yf.download() batches many
  symbols into a single network call, which is the most efficient approach.

Public API
----------
# Single quote with fallback
quote = await get_quote("AAPL")

# Many quotes — Finnhub concurrent, yfinance bulk fallback for failures
quotes = await get_quotes(["AAPL", "MSFT", "NVDA", ...])

# Finnhub raw endpoint (for non-quote calls like /news, /stock/earnings)
data = await finnhub_get(client, "/news", {"category": "general"})

# AV analytics batch (enrichment, not quotes)
analytics = await av_analytics_batch(["IGV", "SOXX", ...], range_="1month")
av_calls_left = av_remaining_calls()
"""
import asyncio
import logging
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import httpx
import yfinance as yf
from google.cloud import firestore

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_FINNHUB_BASE = "https://finnhub.io/api/v1"
_AV_BASE = "https://www.alphavantage.co/query"
_AV_ANALYTICS_BASE = "https://alphavantageapi.co/timeseries/analytics"
_KEY_PATTERN = re.compile(r"token=[^&\s]+")

# Finnhub: stay under 30 req/s hard limit
_FH_SEMAPHORE = asyncio.Semaphore(25)
_FH_REQUEST_DELAY = 0.05  # 50ms → ~20 req/s max under full concurrency

# Alpha Vantage: 25 calls/day free tier; keep 5-call buffer
_AV_DAILY_LIMIT = 20
_AV_SYMBOLS_PER_CALL = 5

# yfinance: synchronous library — run in thread pool
# Semaphore caps concurrent yfinance calls to avoid rapid-burst 429s.
# Target: ~40–80 req/min (well under the ~100–200/min threshold).
_YF_EXECUTOR = ThreadPoolExecutor(max_workers=4)
_YF_SEMAPHORE = asyncio.Semaphore(4)
_YF_DELAY_MIN = 0.5   # seconds — randomized delay mimics human behavior
_YF_DELAY_MAX = 1.5
# Real browser User-Agent reduces bot-detection risk
_YF_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# ── Firestore ─────────────────────────────────────────────────────────────────

_fs_client: firestore.Client | None = None


def _fs() -> firestore.Client:
    global _fs_client
    if _fs_client is None:
        _fs_client = firestore.Client(project=os.environ["GCP_PROJECT_ID"])
    return _fs_client


def get_cache(key: str) -> dict | None:
    """Read a value from Firestore cache. Returns None if missing or expired."""
    doc = _fs().collection("gcp3_cache").document(key).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    expires_at = data.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > datetime.now(timezone.utc):
            return data.get("value")
    return None


def set_cache(key: str, value: dict, ttl_hours: int = 1) -> None:
    """Write a value to Firestore cache with a TTL."""
    now = datetime.now(timezone.utc)
    _fs().collection("gcp3_cache").document(key).set({
        "value": value,
        "expires_at": now + timedelta(hours=ttl_hours),
        "updated_at": now,
    })


# ── Finnhub ───────────────────────────────────────────────────────────────────

def _fh_sanitize(msg: str) -> str:
    """Strip any API key that leaked into an error string."""
    return _KEY_PATTERN.sub("token=<redacted>", msg)


def _fh_headers() -> dict[str, str]:
    return {"X-Finnhub-Token": os.environ["FINNHUB_API_KEY"]}


# Rolling 429 counter — reset each time a successful request completes.
# Lets the debug command detect sustained rate-limiting without log-scanning.
_fh_429_count: int = 0
_fh_429_since: datetime | None = None


def fh_429_stats() -> dict:
    """Return current Finnhub 429 rolling stats for debug endpoints."""
    return {
        "count": _fh_429_count,
        "since": _fh_429_since.isoformat() if _fh_429_since else None,
    }


async def finnhub_get(
    client: httpx.AsyncClient,
    path: str,
    params: dict | None = None,
) -> dict:
    """GET a Finnhub endpoint.

    - API key sent via header, never in the URL.
    - Error messages are sanitized to remove the key.
    - Global semaphore + 50ms delay keeps throughput under 30 req/s.
    - Retries once on HTTP 429 with a 2-second backoff.
    """
    global _fh_429_count, _fh_429_since
    async with _FH_SEMAPHORE:
        await asyncio.sleep(_FH_REQUEST_DELAY)
        try:
            r = await client.get(
                f"{_FINNHUB_BASE}{path}",
                params=params,
                headers=_fh_headers(),
            )
            if r.status_code == 429:
                _fh_429_count += 1
                if _fh_429_since is None:
                    _fh_429_since = datetime.now(timezone.utc)
                logger.warning(
                    "finnhub: rate_limited_429 path=%s total_429s=%d since=%s — waiting 2s",
                    path, _fh_429_count, _fh_429_since.isoformat(),
                )
                await asyncio.sleep(2.0)
                r = await client.get(
                    f"{_FINNHUB_BASE}{path}",
                    params=params,
                    headers=_fh_headers(),
                )
            if r.status_code != 429:
                # Reset counter on any non-429 success
                _fh_429_count = 0
                _fh_429_since = None
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            raise httpx.HTTPStatusError(
                _fh_sanitize(str(exc)),
                request=exc.request,
                response=exc.response,
            ) from None
        except Exception as exc:
            raise type(exc)(_fh_sanitize(str(exc))) from None


async def _finnhub_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    d = await finnhub_get(client, "/quote", {"symbol": symbol})
    return {
        "price": round(d["c"], 2),
        "change": round(d["d"], 2),
        "change_pct": round(d["dp"], 2),
        "high": round(d["h"], 2),
        "low": round(d["l"], 2),
        "open": round(d["o"], 2),
        "prev_close": round(d["pc"], 2),
        "source": "finnhub",
    }


# ── yfinance ──────────────────────────────────────────────────────────────────

def _yf_session() -> "requests.Session":
    """Create an httpx-compatible requests session with a browser User-Agent."""
    import requests
    session = requests.Session()
    session.headers.update({"User-Agent": _YF_USER_AGENT})
    return session


def _yf_quote_sync(symbol: str) -> dict:
    ticker = yf.Ticker(symbol, session=_yf_session())
    hist = ticker.history(period="2d")
    if hist.empty:
        raise ValueError(f"yfinance: no data for {symbol}")
    close_today = float(hist["Close"].iloc[-1])
    close_prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else close_today
    change = round(close_today - close_prev, 2)
    change_pct = round((change / close_prev) * 100, 2) if close_prev else 0.0
    return {
        "price": round(close_today, 2),
        "change": change,
        "change_pct": change_pct,
        "high": round(float(hist["High"].iloc[-1]), 2),
        "low": round(float(hist["Low"].iloc[-1]), 2),
        "open": round(float(hist["Open"].iloc[-1]), 2),
        "prev_close": round(close_prev, 2),
        "source": "yfinance",
    }


def _yf_bulk_sync(symbols: list[str]) -> dict[str, dict]:
    # yf.download batches all symbols in one request — most efficient approach
    tickers = yf.download(symbols, period="2d", auto_adjust=True, progress=False, threads=True)
    results: dict[str, dict] = {}
    if tickers.empty:
        return results
    close = tickers["Close"]
    high = tickers["High"]
    low = tickers["Low"]
    open_ = tickers["Open"]
    for sym in symbols:
        try:
            if sym not in close.columns:
                continue
            sym_close = close[sym].dropna()
            if len(sym_close) < 1:
                continue
            close_today = float(sym_close.iloc[-1])
            close_prev = float(sym_close.iloc[-2]) if len(sym_close) > 1 else close_today
            change = round(close_today - close_prev, 2)
            change_pct = round((change / close_prev) * 100, 2) if close_prev else 0.0
            results[sym] = {
                "price": round(close_today, 2),
                "change": change,
                "change_pct": change_pct,
                "high": round(float(high[sym].iloc[-1]), 2),
                "low": round(float(low[sym].iloc[-1]), 2),
                "open": round(float(open_[sym].iloc[-1]), 2),
                "prev_close": round(close_prev, 2),
                "source": "yfinance",
            }
        except Exception as exc:
            logger.warning("yfinance: failed to parse %s: %s", sym, exc)
    return results


# ── Alpha Vantage ─────────────────────────────────────────────────────────────

_av_call_count: int = 0
_av_call_date: date = date.today()


def _av_reset_if_new_day() -> None:
    global _av_call_count, _av_call_date
    today = date.today()
    if today != _av_call_date:
        _av_call_count = 0
        _av_call_date = today


def av_remaining_calls() -> int:
    """How many Alpha Vantage calls remain today (soft limit: 20 of 25)."""
    _av_reset_if_new_day()
    return max(0, _AV_DAILY_LIMIT - _av_call_count)


def _av_increment() -> None:
    global _av_call_count
    _av_reset_if_new_day()
    _av_call_count += 1


async def _av_fixed_window(
    client: httpx.AsyncClient,
    symbols: list[str],
    range_: str,
    calculations: str = "CUMULATIVE_RETURN,MEAN,STDDEV",
) -> dict:
    api_key = os.environ.get("ALPHA_VANTAGE_KEY")
    if not api_key:
        raise RuntimeError("ALPHA_VANTAGE_KEY not set")
    if av_remaining_calls() <= 0:
        raise RuntimeError("Alpha Vantage daily quota exhausted")

    _av_increment()
    logger.info(
        "alphavantage: ANALYTICS_FIXED_WINDOW symbols=%s range=%s calls_used=%d/%d",
        ",".join(symbols), range_, _av_call_count, _AV_DAILY_LIMIT,
    )
    r = await client.get(
        _AV_ANALYTICS_BASE,
        params={
            "SYMBOLS": ",".join(symbols),
            "RANGE": range_,
            "INTERVAL": "DAILY",
            "OHLC": "close",
            "CALCULATIONS": calculations,
            "apikey": api_key,
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def _av_parse(raw: dict, symbols: list[str]) -> dict[str, dict]:
    payload = raw.get("payload", {})
    results: dict[str, dict] = {}
    for sym in symbols:
        returns_data = payload.get(sym, {}).get("Returns", {})
        results[sym] = {
            "cumulative_return": returns_data.get("CUMULATIVE_RETURN"),
            "mean": returns_data.get("MEAN"),
            "stddev": returns_data.get("STDDEV"),
            "source": "alpha_vantage",
        }
    return results


async def av_analytics_batch(
    symbols: list[str],
    range_: str = "1month",
) -> dict[str, dict]:
    """Fetch AV analytics for symbols, batching 5 per call (free tier max).

    Returns {} immediately if ALPHA_VANTAGE_KEY is not set or quota is gone.
    Symbols from skipped batches (quota mid-run) are absent from the result.
    """
    if not os.environ.get("ALPHA_VANTAGE_KEY"):
        logger.warning("alphavantage: ALPHA_VANTAGE_KEY not set — skipping")
        return {}

    batches = [symbols[i: i + _AV_SYMBOLS_PER_CALL] for i in range(0, len(symbols), _AV_SYMBOLS_PER_CALL)]
    logger.info(
        "alphavantage: %d symbols → %d batches range=%s quota_remaining=%d",
        len(symbols), len(batches), range_, av_remaining_calls(),
    )
    all_results: dict[str, dict] = {}
    async with httpx.AsyncClient() as client:
        for batch in batches:
            if av_remaining_calls() <= 0:
                logger.warning("alphavantage: quota exhausted mid-run — skipping remaining batches")
                break
            try:
                raw = await _av_fixed_window(client, batch, range_)
                all_results.update(_av_parse(raw, batch))
            except Exception as exc:
                logger.error("alphavantage: batch %s failed: %s", batch, exc)
    return all_results


# ── Unified public API ────────────────────────────────────────────────────────

async def get_quote(symbol: str, client: httpx.AsyncClient | None = None) -> dict:
    """Fetch a single quote: Finnhub → yfinance fallback.

    Args:
        symbol: Ticker symbol.
        client: Optional shared httpx client. Creates a new one if not provided.
    """
    async def _fetch(c: httpx.AsyncClient) -> dict:
        try:
            return await _finnhub_quote(c, symbol)
        except Exception as fh_exc:
            logger.warning("data_client: Finnhub failed for %s (%s) — trying yfinance", symbol, fh_exc)
            async with _YF_SEMAPHORE:
                await asyncio.sleep(random.uniform(_YF_DELAY_MIN, _YF_DELAY_MAX))
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(_YF_EXECUTOR, _yf_quote_sync, symbol)

    if client is not None:
        return await _fetch(client)
    async with httpx.AsyncClient(timeout=15) as c:
        return await _fetch(c)


async def get_quotes(
    symbols: list[str],
    client: httpx.AsyncClient | None = None,
) -> dict[str, dict]:
    """Fetch quotes for many symbols: Finnhub concurrent → yfinance bulk fallback.

    Returns:
        {symbol: quote_dict}. Failed symbols (both sources) are absent.
    """
    async def _fetch_all(c: httpx.AsyncClient) -> dict[str, dict]:
        outcomes = await asyncio.gather(
            *[_fetch_one(c, s) for s in symbols], return_exceptions=False
        )
        results: dict[str, dict] = {}
        failed: list[str] = []
        for sym, quote, exc in outcomes:
            if quote is not None:
                results[sym] = quote
            else:
                logger.warning("data_client: Finnhub failed for %s (%s) — queueing yfinance", sym, exc)
                failed.append(sym)

        if failed:
            logger.info("data_client: fetching %d failed symbols via yfinance bulk", len(failed))
            try:
                # Bulk download is one network request regardless of symbol count —
                # acquire semaphore once, add a single randomized delay.
                async with _YF_SEMAPHORE:
                    await asyncio.sleep(random.uniform(_YF_DELAY_MIN, _YF_DELAY_MAX))
                    loop = asyncio.get_event_loop()
                    yf_quotes = await loop.run_in_executor(_YF_EXECUTOR, _yf_bulk_sync, failed)
                results.update(yf_quotes)
                still_failed = [s for s in failed if s not in yf_quotes]
                if still_failed:
                    logger.error("data_client: all sources failed for: %s", still_failed)
            except Exception as exc:
                logger.error("data_client: yfinance bulk failed: %s", exc)

        return results

    async def _fetch_one(c: httpx.AsyncClient, sym: str):
        try:
            q = await _finnhub_quote(c, sym)
            return sym, q, None
        except Exception as exc:
            return sym, None, exc

    if client is not None:
        return await _fetch_all(client)
    async with httpx.AsyncClient(timeout=15) as c:
        return await _fetch_all(c)
