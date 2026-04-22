"""Stock Screener: top movers from major indices + AI momentum signal.

Data resolution chain:
  1. Finnhub — real-time intraday quotes (primary)
  2. yfinance bulk download — free fallback for any symbols Finnhub fails
     (single yf.download() call covers all failed symbols at once)
  3. Massive — fundamentals enrichment (P/E, short interest)
"""
import logging
from datetime import date

from data_client import get_quotes
from firestore import get_cache, set_cache
from massive_client import get_snapshots

logger = logging.getLogger(__name__)

# High-conviction tickers across 54 ETFs (from tickers3.csv)
WATCHLIST: list[str] = [
    "AA", "AAL", "AAPL", "ABB", "ABBV", "ABNB", "ABT", "ACN", "ADBE", "ADM",
    "ADYEN", "AGNC", "AKAM", "ALB", "ALL", "AMD", "AMGN", "AMZN", "AVGO", "AXP",
    "BA", "BAC", "BDX", "BE", "BG", "BHP", "BIDU", "BKNG", "BMY", "BPOP",
    "C", "CB", "CCJ", "CEG", "CF", "CHWY", "COHR", "COP", "CORT", "COST",
    "CRM", "CRWD", "CSX", "CTVA", "CURLF", "CVNA", "CVS", "CVX", "CYPSW", "DAL",
    "DE", "DFS", "DHI", "DHR", "DIS", "DLR", "DOCN", "DUK", "EA", "ELV",
    "ELVN", "EMR", "EQIX", "ETN", "ETSY", "EW", "EXPE", "EXR", "F", "FANUY",
    "FCX", "FIGS", "FIS", "FRPT", "FSLR", "FTNT", "GE", "GILD", "GM", "GO",
    "GOOG", "GOOGL", "GTBIF", "HCA", "HD", "HON", "HSYCF", "HWM", "IDXX", "INTC",
    "INTU", "IPGP", "ISRG", "JNJ", "JPM", "JWN", "KARKF", "KDXHF", "KO", "KR",
    "KUASF", "KYCCF", "LEN", "LIN", "LLY", "LOW", "LQDT", "LUV", "LVS", "LYV",
    "MA", "MAR", "MCD", "MDLZ", "META", "MOD", "MOS", "MRK", "MSFT", "MSLOF",
    "MT", "MU", "MUSA", "NEE", "NEM", "NFLX", "NHNCF", "NLY", "NPIFF", "NSC",
    "NTDOY", "NTES", "NUE", "NVDA", "NVR", "NXE", "NYCB", "OC", "OGN", "OKLO",
    "OKTA", "ONTO", "ORCL", "OROVY", "PANW", "PCRFY", "PEP", "PFE", "PG", "PGR",
    "PHM", "PINS", "PL", "PLD", "PM", "PSA", "PYPL", "REGN", "RF", "RIO",
    "RITM", "RKLB", "RTNTF", "RTX", "SATS", "SEGXF", "SHOP", "SHW", "SLB", "SNAP",
    "SNOW", "SO", "SPOT", "SQ", "SSDIY", "STLD", "STWD", "SYK", "TCEHY", "TCNNF",
    "TER", "TM", "TMO", "TMUS", "TOL", "TRV", "TRVI", "TSEM", "TSLA", "TSN",
    "TT", "TXN", "UAL", "UEC", "UNH", "UNP", "UPS", "UUUU", "V", "VALE",
    "VICI", "VRNOF", "VRTX", "VSAT", "VZ", "WELL", "WFC", "WMT", "WSM", "X",
    "XOM", "ZBRA", "ZIM", "ZION", "ZM", "ZTS"
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

    logger.info("screener cache miss — fetching %d symbols from Finnhub + Massive", len(WATCHLIST))

    # get_quotes handles Finnhub concurrent + yfinance bulk fallback internally
    raw_quotes = await get_quotes(WATCHLIST)
    quotes = {sym: {**q, "symbol": sym, "signal": _ai_signal(q)} for sym, q in raw_quotes.items()}
    valid = list(quotes.values())

    # Enrich with Massive fundamentals (P/E, short interest)
    massive_fundamentals = {}
    try:
        snapshots = await get_snapshots(WATCHLIST)
        for sym in WATCHLIST:
            if sym in snapshots:
                snap = snapshots[sym]
                massive_fundamentals[sym] = {
                    "pe_ratio": snap.get("pe_ratio"),
                    "short_interest": snap.get("short_interest"),
                    "market_cap": snap.get("market_cap"),
                }
                if sym in quotes:
                    quotes[sym]["pe_ratio"] = snap.get("pe_ratio")
                    quotes[sym]["short_interest"] = snap.get("short_interest")
                logger.debug("screener massive: %s = %s", sym, massive_fundamentals[sym])
    except Exception as exc:
        logger.warning("screener massive enrichment failed: %s", exc)

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
        "massive_fundamentals": massive_fundamentals,
    }

    set_cache(cache_key, result, ttl_hours=1)
    return result
