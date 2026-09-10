"""Portfolio Analyzer: fetch live data for a ticker list + AI allocation insights."""
import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

import httpx

from data_client import finnhub_get, get_cache, set_cache

logger = logging.getLogger(__name__)

# Default demo portfolio used when no tickers are provided
DEFAULT_PORTFOLIO: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "JPM", "JNJ", "XOM", "WMT", "GLD",
]


async def _fetch_profile(client: httpx.AsyncClient, symbol: str) -> dict:
    d = await finnhub_get(client, "/stock/profile2", {"symbol": symbol})
    return {"name": d.get("name", symbol), "industry": d.get("finnhubIndustry", ""), "country": d.get("country", "")}


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    d = await finnhub_get(client, "/quote", {"symbol": symbol})
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
        "ai_num_industries": ai["num_industries"],
        "ai_avg_change_pct": ai["avg_change_pct"],
        "ai_insights": ai["insights"],
        "ai_industry_breakdown": ai["industry_breakdown"],
        "ai_winners_count": ai["winners_count"],
        "ai_losers_count": ai["losers_count"],
    }

    set_cache(cache_key, result, ttl_hours=1)
    return result


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def to_health_contract(raw: dict) -> dict:
    """Adapter: gcp3's `ai_*` analysis fields → the portal's PortfolioHealth
    contract (`score` 0-100, `factors[]`, `summary`, `generated_at`).

    The two sides share no field names natively (see
    nuwrrrld-portal docs/wiki-portal/incident-2026-07-26-portfolio-health-endpoint-missing.md) —
    this function is the only place that bridges them. A missing/zero `score`
    here renders as Grade F on the portal, so every field must degrade to a
    defined value, never be omitted.

    Score deliberately excludes `avg_change_pct` (today's price move) — baking
    daily noise into the headline number would make it jumpy day to day, which
    defeats the point of a number users check as a habit. Momentum is reported
    only as an informational factor.
    """
    concentration = float(raw.get("ai_concentration") or 0.0)
    num_industries = int(raw.get("ai_num_industries") or 0)
    avg_change_pct = float(raw.get("ai_avg_change_pct") or 0.0)
    insights = raw.get("ai_insights") or []

    diversification_component = min(num_industries, 6) / 6 * 55
    concentration_component = (1 - concentration) * 45
    score = round(_clamp(diversification_component + concentration_component, 0, 100))

    def _impact(value: float, positive_at: float, negative_at: float) -> str:
        if value >= positive_at:
            return "positive"
        if value <= negative_at:
            return "negative"
        return "neutral"

    factors = [
        {
            "name": "Diversification",
            "score": round(_clamp(min(num_industries, 6) / 6 * 100, 0, 100)),
            "impact": _impact(num_industries, 5, 2),
            "description": f"Holdings span {num_industries} industr{'y' if num_industries == 1 else 'ies'}.",
        },
        {
            "name": "Concentration",
            "score": round(_clamp((1 - concentration) * 100, 0, 100)),
            "impact": "negative" if concentration > 0.5 else ("positive" if concentration < 0.35 else "neutral"),
            "description": f"Largest single-industry concentration is {concentration * 100:.0f}% of holdings.",
        },
        {
            "name": "Momentum",
            "score": round(_clamp(50 + avg_change_pct * 10, 0, 100)),
            "impact": _impact(avg_change_pct, 0.5, -0.5),
            "description": f"Portfolio averaged {avg_change_pct:+.2f}% today (informational — not part of the score).",
        },
    ]

    summary = " ".join(insights[:3]) if insights else "Not enough holding data to summarize."

    return {
        "score": score,
        "factors": factors,
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
