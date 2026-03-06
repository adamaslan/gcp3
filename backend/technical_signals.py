"""Technical Signals: reads per-ticker AI signals from shared Firestore analysis collection."""
import logging
import os
from datetime import date, datetime

from google.cloud import firestore

from firestore import get_cache, set_cache

logger = logging.getLogger(__name__)

# Tickers tracked in the analysis collection by gcp-app-w-mcp1
TRACKED_SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
    "SPY", "QQQ", "IWM", "DIA",
    "JPM", "BAC", "GS", "XLF",
    "JNJ", "UNH", "LLY",
    "XOM", "CVX",
    "COST", "WMT",
]

_ACTION_ORDER = {"BUY": 0, "HOLD": 1, "SELL": 2}


def _db() -> firestore.Client:
    return firestore.Client(project=os.environ["GCP_PROJECT_ID"])


def _serialize(doc: dict) -> dict:
    """Convert Firestore timestamps to strings."""
    out = {}
    for k, v in doc.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, list):
            out[k] = [_serialize(i) if isinstance(i, dict) else i for i in v]
        elif isinstance(v, dict):
            out[k] = _serialize(v)
        else:
            out[k] = v
    return out


async def get_technical_signals(symbol: str | None = None) -> dict:
    cache_key = f"technical_signals:{symbol or 'all'}:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("technical_signals cache hit key=%s", cache_key)
        return cached

    logger.info("technical_signals reading from Firestore analysis collection symbol=%s", symbol or "all")
    db = _db()
    col = db.collection("analysis")

    if symbol:
        doc = col.document(symbol.upper()).get()
        if not doc.exists:
            return {"date": str(date.today()), "symbol": symbol.upper(), "error": "not found"}
        data = _serialize(doc.to_dict())
        data["symbol"] = symbol.upper()
        result = {"date": str(date.today()), "symbols": {symbol.upper(): data}, "total": 1}
    else:
        docs = list(col.stream())
        symbols_data = {}
        for d in docs:
            symbols_data[d.id] = _serialize(d.to_dict())
            symbols_data[d.id]["symbol"] = d.id

        # Sort: BUY first, then HOLD, then SELL; within each by signal_count desc
        ranked = sorted(
            [v for v in symbols_data.values() if "ai_action" in v],
            key=lambda x: (_ACTION_ORDER.get(x.get("ai_action", "HOLD"), 1), -(x.get("signal_count", 0))),
        )
        buys = [r for r in ranked if r.get("ai_action") == "BUY"]
        sells = [r for r in ranked if r.get("ai_action") == "SELL"]
        holds = [r for r in ranked if r.get("ai_action") == "HOLD"]

        result = {
            "date": str(date.today()),
            "total": len(symbols_data),
            "symbols": symbols_data,
            "ranked": ranked,
            "buys": buys,
            "sells": sells,
            "holds": holds,
            "signal_summary": {
                "buy_count": len(buys),
                "sell_count": len(sells),
                "hold_count": len(holds),
                "ai_regime": "Bearish" if len(sells) > len(buys) * 1.5 else "Bullish" if len(buys) > len(sells) * 1.5 else "Mixed",
            },
        }

    set_cache(cache_key, result, ttl_hours=2)
    return result
