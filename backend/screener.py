"""Stock Screener: top movers from major indices + AI momentum signal.

Data resolution chain:
  1. Finnhub — real-time intraday quotes (primary)
  2. yfinance bulk download — free fallback for any symbols Finnhub fails
     (single yf.download() call covers all failed symbols at once)
"""
import logging
from datetime import date

from data_client import get_cache, get_quotes, set_cache

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

    # get_quotes handles Finnhub concurrent + yfinance bulk fallback internally
    raw_quotes = await get_quotes(WATCHLIST)
    quotes = {sym: {**q, "symbol": sym, "signal": _ai_signal(q)} for sym, q in raw_quotes.items()}
    valid = list(quotes.values())

    ranked = sorted(valid, key=lambda x: x.get("change_pct", 0), reverse=True)
    gainers = ranked[:10]
    losers = ranked[-10:][::-1]

    signal_counts: dict[str, int] = {}
    for q in valid:
        sig = q.get("signal", "hold")
        signal_counts[sig] = signal_counts.get(sig, 0) + 1

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
        "sources": {
            "finnhub": sum(1 for q in quotes.values() if q.get("source") == "finnhub"),
            "yfinance": sum(1 for q in quotes.values() if q.get("source") == "yfinance"),
        },
    }

    set_cache(cache_key, result, ttl_hours=1)
    return result
