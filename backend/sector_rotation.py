"""Sector Rotation: momentum scores across 11 GICS sectors + AI regime."""
import asyncio
import logging
import os
from datetime import date

import httpx

import finnhub
from firestore import get_cache, set_cache

logger = logging.getLogger(__name__)

# 11 GICS sectors → primary ETF
SECTORS: dict[str, str] = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}

# Momentum look-back proxied from quote data (intraday only on free tier)
# We score momentum from: change_pct weight 60% + position_in_range 40%
def _momentum_score(q: dict) -> float:
    pct = q.get("change_pct", 0.0)
    price = q.get("price", 0.0)
    low = q.get("low", price)
    high = q.get("high", price)
    intraday_range = high - low
    pos = (price - low) / intraday_range if intraday_range > 0 else 0.5
    return round(0.6 * pct + 0.4 * (pos * 2 - 1) * abs(pct), 3)


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    d = await finnhub.get(client, "/quote", {"symbol": symbol})
    return {
        "price": round(d["c"], 2),
        "change": round(d["d"], 2),
        "change_pct": round(d["dp"], 2),
        "high": round(d["h"], 2),
        "low": round(d["l"], 2),
        "open": round(d["o"], 2),
        "prev_close": round(d["pc"], 2),
    }


def _ai_rotation_analysis(ranked: list[dict]) -> str:
    """Generate a rotation narrative from the ranked sectors."""
    if not ranked:
        return "Insufficient data for rotation analysis."

    top3 = [r["sector"] for r in ranked[:3]]
    bot3 = [r["sector"] for r in ranked[-3:]]
    top_score = ranked[0]["momentum_score"]
    bot_score = ranked[-1]["momentum_score"]
    spread = round(top_score - bot_score, 2)

    offensive = {"Technology", "Consumer Discretionary", "Financials", "Communication Services"}
    defensive = {"Utilities", "Consumer Staples", "Healthcare", "Real Estate"}

    top_set = set(top3)
    if top_set & offensive:
        regime = "offensive"
    elif top_set & defensive:
        regime = "defensive"
    else:
        regime = "neutral"

    return (
        f"Rotation is {regime}. Leading sectors: {', '.join(top3)}. "
        f"Lagging sectors: {', '.join(bot3)}. "
        f"Spread between top and bottom: {spread:.2f} pts — "
        + ("wide divergence signals strong conviction." if abs(spread) > 1.5 else "narrow spread suggests indecision.")
    )


async def get_sector_rotation() -> dict:
    cache_key = f"sector_rotation:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("sector_rotation cache hit key=%s", cache_key)
        return cached

    logger.info("sector_rotation cache miss — fetching %d sectors", len(SECTORS))

    async def fetch_sector(name: str, etf: str):
        try:
            q = await _fetch_quote(client, etf)
            score = _momentum_score(q)
            return name, {"sector": name, "etf": etf, "momentum_score": score, **q}
        except Exception as exc:
            logger.error("sector_rotation failed %s (%s): %s", name, etf, exc)
            return name, {"sector": name, "etf": etf, "error": str(exc)}

    async with httpx.AsyncClient(timeout=15) as client:
        pairs = await asyncio.gather(*[fetch_sector(n, e) for n, e in SECTORS.items()])

    sectors_raw = dict(pairs)
    valid = [v for v in sectors_raw.values() if "momentum_score" in v]
    ranked = sorted(valid, key=lambda x: x["momentum_score"], reverse=True)

    result = {
        "date": str(date.today()),
        "sectors": sectors_raw,
        "ranked": ranked,
        "leaders": ranked[:3],
        "laggards": ranked[-3:],
        "ai_analysis": _ai_rotation_analysis(ranked),
    }

    set_cache(cache_key, result, ttl_hours=2)
    return result
