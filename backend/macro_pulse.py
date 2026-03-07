"""Macro Pulse: VIX, bonds, dollar, gold, oil — macro regime signal."""
import asyncio
import logging
import os
from datetime import date

import httpx

import finnhub
from firestore import get_cache, set_cache

logger = logging.getLogger(__name__)

# Macro proxy ETFs / tickers
MACRO_TICKERS: dict[str, dict] = {
    "VIX": {"ticker": "VIX", "label": "Fear Gauge", "category": "volatility"},
    "TLT": {"ticker": "TLT", "label": "20yr Treasury ETF", "category": "bonds"},
    "SHY": {"ticker": "SHY", "label": "2yr Treasury ETF", "category": "bonds"},
    "DXY": {"ticker": "DXY", "label": "US Dollar Index", "category": "currency"},
    "GLD": {"ticker": "GLD", "label": "Gold ETF", "category": "commodities"},
    "SLV": {"ticker": "SLV", "label": "Silver ETF", "category": "commodities"},
    "USO": {"ticker": "USO", "label": "Oil ETF", "category": "commodities"},
    "UNG": {"ticker": "UNG", "label": "Natural Gas ETF", "category": "commodities"},
    "HYG": {"ticker": "HYG", "label": "High Yield Bond ETF", "category": "credit"},
    "LQD": {"ticker": "LQD", "label": "Investment Grade Bond ETF", "category": "credit"},
    "TIP": {"ticker": "TIP", "label": "TIPS (Inflation)", "category": "inflation"},
}


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    d = await finnhub.get(client, "/quote", {"symbol": symbol})
    return {
        "price": round(d["c"], 2),
        "change_pct": round(d["dp"], 2),
        "change": round(d["d"], 2),
        "high": round(d["h"], 2),
        "low": round(d["l"], 2),
    }


def _ai_macro_regime(data: dict) -> str:
    """Classify macro regime from indicator readings."""
    vix = data.get("VIX", {}).get("price")
    tlt = data.get("TLT", {}).get("change_pct")
    gld = data.get("GLD", {}).get("change_pct")
    hyg = data.get("HYG", {}).get("change_pct")
    dxy = data.get("DXY", {}).get("change_pct")
    uso = data.get("USO", {}).get("change_pct")
    tip = data.get("TIP", {}).get("change_pct")

    signals = []
    regime_score = 0  # positive = risk-on, negative = risk-off

    if vix is not None:
        if vix > 30:
            signals.append("VIX above 30 — elevated fear")
            regime_score -= 2
        elif vix > 20:
            signals.append("VIX moderately elevated")
            regime_score -= 1
        else:
            signals.append("VIX below 20 — calm conditions")
            regime_score += 1

    if tlt is not None:
        if tlt > 0.5:
            signals.append("Bonds rallying — flight to safety")
            regime_score -= 1
        elif tlt < -0.5:
            signals.append("Bonds selling off — yields rising")
            regime_score += 1

    if gld is not None and gld > 0.5:
        signals.append("Gold rising — inflation/uncertainty hedge active")
        regime_score -= 1

    if hyg is not None:
        if hyg > 0.3:
            signals.append("Credit spreads tightening — risk appetite strong")
            regime_score += 1
        elif hyg < -0.3:
            signals.append("Credit spreads widening — risk-off credit signal")
            regime_score -= 1

    if dxy is not None and dxy > 0.5:
        signals.append("Dollar strengthening — global risk-off")
        regime_score -= 1

    if uso is not None and uso > 1:
        signals.append("Oil rising — inflationary pressure")

    if tip is not None and tip > 0.3:
        signals.append("TIPS rising — inflation expectations elevated")

    if regime_score >= 2:
        regime = "Risk-On"
        summary = "Macro backdrop is supportive. Equity-positive conditions."
    elif regime_score <= -2:
        regime = "Risk-Off"
        summary = "Macro signals are defensive. Reduce equity exposure; favor bonds/gold."
    else:
        regime = "Transitional"
        summary = "Mixed macro signals. Monitor VIX and credit spreads for confirmation."

    return {
        "regime": regime,
        "regime_score": regime_score,
        "signals": signals,
        "summary": summary,
    }


async def get_macro_pulse() -> dict:
    cache_key = f"macro_pulse:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("macro_pulse cache hit key=%s", cache_key)
        return cached

    logger.info("macro_pulse cache miss — fetching %d tickers", len(MACRO_TICKERS))

    async def fetch_one(key: str, meta: dict):
        try:
            q = await _fetch_quote(client, meta["ticker"])
            return key, {**meta, **q}
        except Exception as exc:
            logger.error("macro_pulse failed %s: %s", key, exc)
            return key, {**meta, "error": str(exc)}

    async with httpx.AsyncClient(timeout=15) as client:
        pairs = await asyncio.gather(*[fetch_one(k, m) for k, m in MACRO_TICKERS.items()])

    indicators = dict(pairs)
    ai_analysis = _ai_macro_regime({k: v for k, v in indicators.items() if "error" not in v})

    # Group by category
    by_category: dict[str, list] = {}
    for k, v in indicators.items():
        cat = v.get("category", "other")
        by_category.setdefault(cat, []).append(v)

    result = {
        "date": str(date.today()),
        "indicators": indicators,
        "by_category": by_category,
        "ai_regime": ai_analysis["regime"],
        "ai_regime_score": ai_analysis["regime_score"],
        "ai_signals": ai_analysis["signals"],
        "ai_summary": ai_analysis["summary"],
    }

    set_cache(cache_key, result, ttl_hours=2)
    return result
