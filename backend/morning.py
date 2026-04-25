"""Morning Brief: daily market tone from major index ETFs."""
import asyncio
import logging
from datetime import date

import httpx

from data_client import finnhub_get
from firestore import get_cache, set_cache
from data_client import get_finnhub_metrics

logger = logging.getLogger(__name__)

INDICES = {
    "S&P 500": "SPY",
    "Nasdaq 100": "QQQ",
    "Russell 2000": "IWM",
    "Dow Jones": "DIA",
}


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    d = await finnhub_get(client, "/quote", {"symbol": symbol})
    return {
        "price": d["c"],
        "change": round(d["d"], 2),
        "change_pct": round(d["dp"], 2),
        "open": round(d["o"], 2),
        "prev_close": round(d["pc"], 2),
        "high": round(d["h"], 2),
        "low": round(d["l"], 2),
    }


async def get_morning_brief() -> dict:
    cache_key = f"morning:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("morning_brief cache hit key=%s", cache_key)
        return cached

    logger.info("morning_brief cache miss key=%s — fetching from Finnhub + Massive", cache_key)

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

    # Enrich with Finnhub 52w high/low (only 4-5 index symbols — well within free tier)
    metrics: dict[str, dict] = {}
    try:
        metrics = await get_finnhub_metrics(list(INDICES.values()))
        for symbol, m in metrics.items():
            logger.debug("morning_brief metrics: %s = %s", symbol, m)
    except Exception as exc:
        logger.warning("morning_brief metrics enrichment failed: %s", exc)

    result = {
        "date": str(date.today()),
        "market_tone": tone,
        "avg_change_pct": round(avg_change, 2),
        "indices": indices,
        "metrics_52w": metrics,
        "summary": (
            f"Markets are {tone} today with an average move of {avg_change:+.2f}% "
            f"across major indices."
        ),
    }

    set_cache(cache_key, result, ttl_hours=8)
    return result
