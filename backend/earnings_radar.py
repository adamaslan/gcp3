"""Earnings Radar: upcoming earnings calendar + surprise history + AI outlook."""
import asyncio
import logging
import os
from datetime import date, timedelta

import httpx

from firestore import get_cache, set_cache

logger = logging.getLogger(__name__)

# High-profile tickers to track for earnings
TRACKED: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "JPM", "BAC", "GS", "MS",
    "JNJ", "UNH", "LLY", "PFE",
    "XOM", "CVX",
    "DIS", "NFLX",
    "WMT", "COST", "HD",
]


async def _fetch_earnings_calendar(client: httpx.AsyncClient, symbol: str) -> dict | None:
    """Fetch next earnings date and EPS estimate from Finnhub."""
    try:
        r = await client.get(
            "https://finnhub.io/api/v1/stock/earnings",
            params={"symbol": symbol, "token": os.environ["FINNHUB_API_KEY"]},
        )
        r.raise_for_status()
        items = r.json()
        if not items:
            return None
        # Most recent / upcoming — sorted by date desc
        latest = items[0] if items else None
        if not latest:
            return None
        return {
            "symbol": symbol,
            "period": latest.get("period"),
            "actual": latest.get("actual"),
            "estimate": latest.get("estimate"),
            "surprise": latest.get("surprisePercent"),
            "year": latest.get("year"),
            "quarter": latest.get("quarter"),
        }
    except Exception as exc:
        logger.error("earnings_radar fetch failed %s: %s", symbol, exc)
        return None


def _ai_earnings_outlook(records: list[dict]) -> str:
    """Summarize earnings beat/miss trends."""
    if not records:
        return "No earnings data available."

    beats = [r for r in records if r.get("surprise") is not None and r["surprise"] > 0]
    misses = [r for r in records if r.get("surprise") is not None and r["surprise"] < 0]
    beat_rate = round(len(beats) / len(records) * 100) if records else 0

    top_beat = max(beats, key=lambda x: x["surprise"], default=None)
    top_miss = min(misses, key=lambda x: x["surprise"], default=None)

    outlook = f"{beat_rate}% of tracked companies beat estimates last quarter. "
    if top_beat:
        outlook += f"Biggest beat: {top_beat['symbol']} (+{top_beat['surprise']:.1f}%). "
    if top_miss:
        outlook += f"Biggest miss: {top_miss['symbol']} ({top_miss['surprise']:.1f}%). "
    if beat_rate >= 70:
        outlook += "Strong earnings season — corporate fundamentals are solid."
    elif beat_rate >= 50:
        outlook += "Mixed results — earnings quality is uneven across sectors."
    else:
        outlook += "Weak beat rate — earnings pressure may weigh on equities."
    return outlook


async def get_earnings_radar() -> dict:
    cache_key = f"earnings_radar:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("earnings_radar cache hit key=%s", cache_key)
        return cached

    logger.info("earnings_radar cache miss — fetching %d symbols", len(TRACKED))

    async with httpx.AsyncClient(timeout=20) as client:
        results = await asyncio.gather(*[_fetch_earnings_calendar(client, s) for s in TRACKED])

    records = [r for r in results if r is not None]
    with_surprise = [r for r in records if r.get("surprise") is not None]
    beats = [r for r in with_surprise if r["surprise"] > 0]
    misses = [r for r in with_surprise if r["surprise"] < 0]

    result = {
        "date": str(date.today()),
        "tracked": len(TRACKED),
        "records": records,
        "beats": sorted(beats, key=lambda x: x["surprise"], reverse=True)[:5],
        "misses": sorted(misses, key=lambda x: x["surprise"])[:5],
        "beat_rate_pct": round(len(beats) / len(with_surprise) * 100) if with_surprise else 0,
        "ai_outlook": _ai_earnings_outlook(records),
    }

    set_cache(cache_key, result, ttl_hours=6)
    return result
