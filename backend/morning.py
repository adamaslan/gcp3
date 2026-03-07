"""Morning Brief: daily market tone from major index ETFs."""
import asyncio
import logging
import os
from datetime import date

import httpx

from firestore import get_cache, set_cache

logger = logging.getLogger(__name__)

INDICES = {
    "S&P 500": "SPY",
    "Nasdaq 100": "QQQ",
    "Russell 2000": "IWM",
    "Dow Jones": "DIA",
}


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    url = "https://finnhub.io/api/v1/quote"
    r = await client.get(url, params={"symbol": symbol, "token": os.environ["FINNHUB_API_KEY"]})
    r.raise_for_status()
    d = r.json()
    return {"price": d["c"], "change": round(d["d"], 2), "change_pct": round(d["dp"], 2)}


async def get_morning_brief() -> dict:
    cache_key = f"morning:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("morning_brief cache hit key=%s", cache_key)
        return cached

    logger.info("morning_brief cache miss key=%s — fetching from Finnhub", cache_key)

    async def fetch_index(client, name, symbol):
        try:
            quote = await _fetch_quote(client, symbol)
            logger.info("morning_brief fetched %s (%s): %s", name, symbol, quote)
            return name, {"symbol": symbol, **quote}
        except Exception as exc:
            logger.error("morning_brief failed to fetch %s (%s): %s", name, symbol, exc)
            return name, {"symbol": symbol, "error": str(exc)}

    async with httpx.AsyncClient(timeout=10) as client:
        results = await asyncio.gather(*[fetch_index(client, n, s) for n, s in INDICES.items()])

    indices = dict(results)
    valid = [v for v in indices.values() if "change_pct" in v]
    avg_change = sum(v["change_pct"] for v in valid) / len(valid) if valid else 0
    tone = "bullish" if avg_change > 0.5 else "bearish" if avg_change < -0.5 else "neutral"

    result = {
        "date": str(date.today()),
        "market_tone": tone,
        "avg_change_pct": round(avg_change, 2),
        "indices": indices,
        "summary": (
            f"Markets are {tone} today with an average move of {avg_change:+.2f}% "
            f"across major indices."
        ),
    }

    set_cache(cache_key, result, ttl_hours=8)
    return result
