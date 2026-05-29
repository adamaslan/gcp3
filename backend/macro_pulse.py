"""Macro Pulse: VIX, bonds, dollar, gold, oil — macro regime signal."""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx

from data_client import finnhub_get
from firestore import get_cache, set_cache
from data_client import get_finnhub_metrics

logger = logging.getLogger(__name__)

_YF_EXECUTOR = ThreadPoolExecutor(max_workers=2)

# yfinance symbols for macro indicators where Finnhub returns c=0.
# Finnhub's free /quote endpoint cannot price raw indices (VIX, DXY) and
# returns c=0. These yfinance symbols are used as a fallback when the primary
# Finnhub proxy also fails (e.g. VIXY after hours, UUP on thin-volume days).
_YF_MACRO_SYMBOLS: dict[str, str] = {
    "VIX": "^VIX",
    "DXY": "DX-Y.NYB",
}


def _yf_macro_sync(yf_symbol: str) -> dict:
    import requests
    import yfinance as yf
    from data_client import _YF_USER_AGENT
    session = requests.Session()
    session.headers.update({"User-Agent": _YF_USER_AGENT})
    ticker = yf.Ticker(yf_symbol, session=session)
    hist = ticker.history(period="2d")
    if hist.empty:
        raise ValueError(f"yfinance: no data for {yf_symbol}")
    close_today = float(hist["Close"].iloc[-1])
    close_prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else close_today
    change = round(close_today - close_prev, 2)
    change_pct = round((change / close_prev) * 100, 2) if close_prev else 0.0
    return {
        "price": round(close_today, 2),
        "change_pct": change_pct,
        "change": change,
        "high": round(float(hist["High"].iloc[-1]), 2),
        "low": round(float(hist["Low"].iloc[-1]), 2),
        "source": "yfinance",
    }


# Macro proxy ETFs / tickers
# VIX and DXY are indices — Finnhub's free /quote endpoint does not price
# raw indices and returns c=0 for them. Use tradeable ETF proxies Finnhub
# CAN price: VIXY (VIX short-term futures) and UUP (US Dollar Index fund).
# This keeps real prices from a real source — no faked index values.
MACRO_TICKERS: dict[str, dict] = {
    "VIX": {"ticker": "VIXY", "label": "Fear Gauge (VIXY proxy)", "category": "volatility"},
    "TLT": {"ticker": "TLT", "label": "20yr Treasury ETF", "category": "bonds"},
    "SHY": {"ticker": "SHY", "label": "2yr Treasury ETF", "category": "bonds"},
    "DXY": {"ticker": "UUP", "label": "US Dollar Index (UUP proxy)", "category": "currency"},
    "GLD": {"ticker": "GLD", "label": "Gold ETF", "category": "commodities"},
    "SLV": {"ticker": "SLV", "label": "Silver ETF", "category": "commodities"},
    "USO": {"ticker": "USO", "label": "Oil ETF", "category": "commodities"},
    "UNG": {"ticker": "UNG", "label": "Natural Gas ETF", "category": "commodities"},
    "HYG": {"ticker": "HYG", "label": "High Yield Bond ETF", "category": "credit"},
    "LQD": {"ticker": "LQD", "label": "Investment Grade Bond ETF", "category": "credit"},
    "TIP": {"ticker": "TIP", "label": "TIPS (Inflation)", "category": "inflation"},
}


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    d = await finnhub_get(client, "/quote", {"symbol": symbol})
    # Finnhub returns None for c/dp/d/h/l when the symbol has no data (e.g. VIX, DXY)
    def _safe_round(v: float | None) -> float | None:
        return round(v, 2) if v is not None else None

    price = _safe_round(d.get("c"))
    if price is None or price == 0:
        raise ValueError(f"No price data from Finnhub for {symbol} (c={d.get('c')})")
    return {
        "price": price,
        "change_pct": _safe_round(d.get("dp")),
        "change": _safe_round(d.get("d")),
        "high": _safe_round(d.get("h")),
        "low": _safe_round(d.get("l")),
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

    logger.info("macro_pulse cache miss — fetching %d tickers from Finnhub + Massive", len(MACRO_TICKERS))

    async def fetch_one(key: str, meta: dict):
        try:
            q = await _fetch_quote(client, meta["ticker"])
            return key, {**meta, **q}
        except ValueError as exc:
            # Finnhub proxy returned c=0 — try yfinance for known index symbols.
            yf_symbol = _YF_MACRO_SYMBOLS.get(key)
            if yf_symbol:
                try:
                    loop = asyncio.get_running_loop()
                    yf_q = await loop.run_in_executor(_YF_EXECUTOR, _yf_macro_sync, yf_symbol)
                    logger.info("macro_pulse: yfinance fallback ok key=%s yf=%s", key, yf_symbol)
                    return key, {**meta, **yf_q}
                except Exception as yf_exc:
                    logger.warning("macro_pulse: yfinance fallback failed key=%s yf=%s: %s", key, yf_symbol, yf_exc)
            logger.warning("macro_pulse failed %s: %s", key, exc)
            return key, {**meta, "error": str(exc)}
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

    # Enrich with Finnhub 52w high/low (~11 macro tickers — well within free tier)
    metrics_52w: dict[str, dict] = {}
    try:
        metrics_52w = await get_finnhub_metrics(list(MACRO_TICKERS.keys()))
        for key, m in metrics_52w.items():
            logger.debug("macro_pulse metrics: %s = %s", key, m)
    except Exception as exc:
        logger.warning("macro_pulse metrics enrichment failed: %s", exc)

    # An indicator with no Finnhub price data carries an `error` field instead
    # of a quote. The endpoint still returns HTTP 200, so surface completeness
    # explicitly — a silently smaller indicator set otherwise looks complete.
    # See incident-2026-05-21.
    failed_indicators = sorted(k for k, v in indicators.items() if "error" in v)
    data_status = {
        "expected": len(indicators),
        "available": len(indicators) - len(failed_indicators),
        "failed": len(failed_indicators),
        "partial": bool(failed_indicators),
        "failed_indicators": failed_indicators,
    }

    result = {
        "date": str(date.today()),
        "data_status": data_status,
        "indicators": indicators,
        "by_category": by_category,
        "ai_regime": ai_analysis["regime"],
        "ai_regime_score": ai_analysis["regime_score"],
        "ai_signals": ai_analysis["signals"],
        "ai_summary": ai_analysis["summary"],
        "metrics_52w": metrics_52w,
    }

    set_cache(cache_key, result, ttl_hours=2)
    return result
