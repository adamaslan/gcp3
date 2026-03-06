"""Stock Screener: top movers from major indices + AI momentum signal."""
import asyncio
import logging
import os
from datetime import date

import httpx

from firestore import get_cache, set_cache

logger = logging.getLogger(__name__)

# Representative large-caps across sectors
WATCHLIST: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "ORCL", "ADBE",
    "JPM", "BAC", "GS", "MS", "BLK",
    "JNJ", "UNH", "LLY", "PFE", "ABBV",
    "XOM", "CVX", "COP", "SLB",
    "PG", "KO", "PEP", "WMT", "COST",
    "BA", "CAT", "GE", "HON", "LMT",
    "DIS", "NFLX", "SPOT", "CMCSA",
    "GLD", "SLV", "TLT", "HYG",
]


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    r = await client.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": symbol, "token": os.environ["FINNHUB_API_KEY"]},
    )
    r.raise_for_status()
    d = r.json()
    return {
        "symbol": symbol,
        "price": round(d["c"], 2),
        "change": round(d["d"], 2),
        "change_pct": round(d["dp"], 2),
        "high": round(d["h"], 2),
        "low": round(d["l"], 2),
        "open": round(d["o"], 2),
        "prev_close": round(d["pc"], 2),
    }


def _ai_signal(quote: dict) -> str:
    """Rule-based momentum signal derived from intraday data."""
    pct = quote.get("change_pct", 0)
    price = quote.get("price", 0)
    low = quote.get("low", price)
    high = quote.get("high", price)
    intraday_range = high - low
    position_in_range = (price - low) / intraday_range if intraday_range > 0 else 0.5

    if pct > 3 and position_in_range > 0.75:
        return "strong_buy"
    if pct > 1.5 or (pct > 0.5 and position_in_range > 0.7):
        return "buy"
    if pct < -3 and position_in_range < 0.25:
        return "strong_sell"
    if pct < -1.5 or (pct < -0.5 and position_in_range < 0.3):
        return "sell"
    return "hold"


async def get_screener_data() -> dict:
    cache_key = f"screener:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("screener cache hit key=%s", cache_key)
        return cached

    logger.info("screener cache miss — fetching %d symbols", len(WATCHLIST))

    async def fetch_one(symbol: str):
        try:
            q = await _fetch_quote(client, symbol)
            q["signal"] = _ai_signal(q)
            return symbol, q
        except Exception as exc:
            logger.error("screener failed %s: %s", symbol, exc)
            return symbol, {"symbol": symbol, "error": str(exc)}

    async with httpx.AsyncClient(timeout=15) as client:
        pairs = await asyncio.gather(*[fetch_one(s) for s in WATCHLIST])

    quotes = {k: v for k, v in pairs if "error" not in v}
    valid = list(quotes.values())

    ranked = sorted(valid, key=lambda x: x.get("change_pct", 0), reverse=True)
    gainers = ranked[:10]
    losers = ranked[-10:][::-1]

    signal_counts = {}
    for q in valid:
        sig = q.get("signal", "hold")
        signal_counts[sig] = signal_counts.get(sig, 0) + 1

    # AI summary: breadth-based regime
    total = len(valid)
    buys = signal_counts.get("buy", 0) + signal_counts.get("strong_buy", 0)
    sells = signal_counts.get("sell", 0) + signal_counts.get("strong_sell", 0)
    breadth_pct = round((buys - sells) / total * 100, 1) if total else 0
    if breadth_pct > 20:
        regime = "Risk-On: broad buying pressure across watchlist."
    elif breadth_pct < -20:
        regime = "Risk-Off: selling pressure dominates; caution advised."
    else:
        regime = "Mixed: market is rotating — select opportunities only."

    result = {
        "date": str(date.today()),
        "total_screened": total,
        "gainers": gainers,
        "losers": losers,
        "signal_counts": signal_counts,
        "breadth_pct": breadth_pct,
        "ai_regime": regime,
        "quotes": quotes,
    }

    set_cache(cache_key, result, ttl_hours=1)
    return result
