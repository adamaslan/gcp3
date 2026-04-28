"""Stock Screener: top movers across watchlist with rule-based momentum signals.

Data resolution:
  - Reads exclusively from Firestore cache (populated by the nightly refresh job).
  - Returns HTTP 503 if cache is cold — never makes live Finnhub/yfinance calls
    at request time, avoiding rate-limit exposure on hot paths.
  - Cache TTL is 26h so a missed nightly refresh still serves yesterday's data
    rather than going dark.
"""
import asyncio
import logging
from datetime import date

from fastapi import HTTPException
from firestore import get_cache, set_cache
from utils.signals import ai_signal

logger = logging.getLogger(__name__)

# Stampede guard: only one coroutine fetches at a time; others wait and reuse
# the result written to cache by the winner.
_fetch_lock = asyncio.Lock()

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




_SCREENER_TTL_HOURS = 26  # survives one missed nightly refresh


async def get_screener_data() -> dict:
    """Return screener data from Firestore cache.

    Raises:
        HTTPException 503: Cache is cold (nightly refresh hasn't run yet today).
    """
    cache_key = f"screener:{date.today()}"
    cached = get_cache(cache_key)
    if cached is not None:
        logger.info("screener cache_hit key=%s symbols=%s", cache_key, cached.get("total_screened"))
        return cached

    logger.warning("screener cache_miss key=%s — returning 503; nightly refresh has not run", cache_key)
    raise HTTPException(
        status_code=503,
        detail="Screener data not yet available — nightly refresh has not run. Try again after market close.",
    )


async def build_screener_cache() -> dict:
    """Fetch live quotes and write the screener cache. Called by the nightly refresh job only.

    Returns:
        The assembled screener result dict.
    """
    from data_client import get_quotes  # local import — only the refresh job needs this

    cache_key = f"screener:{date.today()}"

    async with _fetch_lock:
        # Re-check after acquiring lock — another job invocation may have just written
        if cached := get_cache(cache_key):
            logger.info("screener build_cache: already populated key=%s — skipping", cache_key)
            return cached

        logger.info("screener build_cache: fetching %d symbols from Finnhub", len(WATCHLIST))
        raw_quotes = await get_quotes(WATCHLIST)
        quotes = {sym: {**q, "symbol": sym, "signal": ai_signal(q)} for sym, q in raw_quotes.items()}
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

        set_cache(cache_key, result, ttl_hours=_SCREENER_TTL_HOURS)
        logger.info(
            "screener build_cache: complete key=%s symbols=%d gainers=%d losers=%d breadth_pct=%s",
            cache_key, total, len(gainers), len(losers), breadth_pct,
        )
        return result
