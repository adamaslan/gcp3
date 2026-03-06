"""Portfolio Analyzer: fetch live data for a ticker list + AI allocation insights."""
import asyncio
import logging
import os
from datetime import date
from typing import Optional

import httpx

import finnhub
from firestore import get_cache, set_cache

logger = logging.getLogger(__name__)

# Default demo portfolio used when no tickers are provided
DEFAULT_PORTFOLIO: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "JPM", "JNJ", "XOM", "WMT", "GLD",
]


async def _fetch_profile(client: httpx.AsyncClient, symbol: str) -> dict:
    d = await finnhub.get(client, "/stock/profile2", {"symbol": symbol})
    return {"name": d.get("name", symbol), "industry": d.get("finnhubIndustry", ""), "country": d.get("country", "")}


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    d = await finnhub.get(client, "/quote", {"symbol": symbol})
    return {
        "price": round(d["c"], 2),
        "change_pct": round(d["dp"], 2),
        "change": round(d["d"], 2),
        "high": round(d["h"], 2),
        "low": round(d["l"], 2),
    }


def _ai_allocation_analysis(holdings: list[dict]) -> dict:
    """Analyze diversification and generate AI insights."""
    if not holdings:
        return {"grade": "N/A", "insights": ["No valid holdings data."]}

    industry_map: dict[str, list[str]] = {}
    for h in holdings:
        ind = h.get("industry") or "Unknown"
        industry_map.setdefault(ind, []).append(h["symbol"])

    total = len(holdings)
    concentration = max(len(v) / total for v in industry_map.values()) if industry_map else 0
    num_industries = len(industry_map)

    avg_change = sum(h.get("change_pct", 0) for h in holdings) / total if total else 0
    winners = [h for h in holdings if h.get("change_pct", 0) > 0]
    losers = [h for h in holdings if h.get("change_pct", 0) < 0]

    insights = []
    if concentration > 0.5:
        top_ind = max(industry_map, key=lambda k: len(industry_map[k]))
        insights.append(f"High concentration in {top_ind} ({len(industry_map[top_ind])}/{total} holdings). Consider diversifying.")
    else:
        insights.append(f"Good diversification across {num_industries} industries.")

    if avg_change > 0.5:
        insights.append(f"Portfolio is up on average {avg_change:+.2f}% today — momentum positive.")
    elif avg_change < -0.5:
        insights.append(f"Portfolio is down on average {avg_change:+.2f}% today — review risk exposure.")
    else:
        insights.append(f"Portfolio roughly flat today ({avg_change:+.2f}% avg).")

    if winners:
        top = max(winners, key=lambda h: h.get("change_pct", 0))
        insights.append(f"Top performer: {top['symbol']} ({top['change_pct']:+.2f}%)")
    if losers:
        bot = min(losers, key=lambda h: h.get("change_pct", 0))
        insights.append(f"Worst performer: {bot['symbol']} ({bot['change_pct']:+.2f}%)")

    if num_industries >= 5 and concentration < 0.35:
        grade = "A"
    elif num_industries >= 3 and concentration < 0.5:
        grade = "B"
    elif num_industries >= 2:
        grade = "C"
    else:
        grade = "D"

    return {
        "grade": grade,
        "concentration": round(concentration, 2),
        "num_industries": num_industries,
        "avg_change_pct": round(avg_change, 2),
        "winners_count": len(winners),
        "losers_count": len(losers),
        "insights": insights,
        "industry_breakdown": {k: v for k, v in industry_map.items()},
    }


import re

_SYMBOL_RE = re.compile(r"^[A-Z]{1,10}$")


def _sanitize_symbol(raw: str) -> str | None:
    """Allow only uppercase alphanumeric ticker symbols (1–10 chars). Returns None if invalid."""
    s = raw.upper().strip()
    return s if _SYMBOL_RE.match(s) else None


async def get_portfolio_analysis(tickers: Optional[list[str]] = None) -> dict:
    raw = [t.strip() for t in (tickers or DEFAULT_PORTFOLIO) if t.strip()]
    symbols = [s for t in raw if (s := _sanitize_symbol(t)) is not None]
    cache_key = f"portfolio:{'_'.join(sorted(symbols))}:{date.today()}"

    if cached := get_cache(cache_key):
        logger.info("portfolio cache hit key=%s", cache_key)
        return cached

    logger.info("portfolio cache miss — fetching %d symbols", len(symbols))

    async def fetch_holding(symbol: str):
        try:
            quote, profile = await asyncio.gather(
                _fetch_quote(client, symbol),
                _fetch_profile(client, symbol),
            )
            return symbol, {"symbol": symbol, **profile, **quote}
        except Exception as exc:
            logger.error("portfolio fetch failed %s: %s", symbol, exc)
            return symbol, {"symbol": symbol, "error": str(exc)}

    async with httpx.AsyncClient(timeout=20) as client:
        pairs = await asyncio.gather(*[fetch_holding(s) for s in symbols])

    holdings_map = dict(pairs)
    valid = [v for v in holdings_map.values() if "error" not in v]

    ai = _ai_allocation_analysis(valid)

    result = {
        "date": str(date.today()),
        "tickers": symbols,
        "holdings": holdings_map,
        "ai_grade": ai["grade"],
        "ai_concentration": ai["concentration"],
        "ai_avg_change_pct": ai["avg_change_pct"],
        "ai_insights": ai["insights"],
        "ai_industry_breakdown": ai["industry_breakdown"],
        "ai_winners_count": ai["winners_count"],
        "ai_losers_count": ai["losers_count"],
    }

    set_cache(cache_key, result, ttl_hours=1)
    return result
