"""Technical Signals: reads per-ticker AI signals from shared Firestore analysis collection."""
import logging
import re
from datetime import date, datetime

from firestore import db as _db, get_cache, set_cache
from industry import INDUSTRIES

logger = logging.getLogger(__name__)

# 54 industry ETFs derived from industry.py — single source of truth
ETF_UNIVERSE: list[str] = [
    etf for sector in INDUSTRIES.values() for etf in sector.values()
]

# 4 primary constituent stocks per ETF (representative holdings, not exhaustive)
ETF_CONSTITUENTS: dict[str, list[str]] = {
    "IGV":  ["MSFT", "ADBE", "NXPI", "SNPS"],
    "SOXX": ["NVDA", "ASML", "AMD", "QCOM"],
    "CLOU": ["MSFT", "CRM", "ADBE", "INTU"],
    "HACK": ["CRWD", "OKTA", "DDOG", "PANW"],
    "BOTZ": ["NVDA", "MSFT", "TSLA", "ASML"],
    "FDN":  ["GOOGL", "META", "MSFT", "AMZN"],
    "XLK":  ["AAPL", "MSFT", "NVDA", "INTC"],
    "VOX":  ["VZ", "T", "TMUS", "CMCSA"],
    "IBB":  ["AMGN", "GILD", "VRTX", "REGN"],
    "XPH":  ["JNJ", "PFE", "AZN", "BMY"],
    "IHF":  ["UNH", "AMEDX", "CVS", "HCA"],
    "IHI":  ["TMO", "ABT", "ISRG", "DXCM"],
    "XLV":  ["UNH", "AMEDX", "BLDP", "VEEV"],
    "VHT":  ["WELL", "OHI", "LTC", "SBRA"],
    "KBE":  ["JPM", "BAC", "WFC", "GS"],
    "KIE":  ["BRK", "PGR", "TRV", "AIG"],
    "PFM":  ["BLK", "AUM", "BEN", "AMG"],
    "FINX": ["SQ", "PYPL", "COIN", "UPST"],
    "REM":  ["NRZ", "AGNC", "ARMOUR", "MFA"],
    "IPAY": ["MA", "V", "AXP", "DFS"],
    "KRE":  ["WAL", "HBAN", "PNC", "FITB"],
    "XRT":  ["AMZN", "TJX", "MCD", "LOW"],
    "IBUY": ["AMZN", "EBAY", "SHOP", "MELI"],
    "XLP":  ["WMT", "PG", "KO", "COST"],
    "ESPO": ["ATVI", "EA", "TTWO", "RBLX"],
    "PAWZ": ["CHWY", "TRUP", "AMEDX", "VSH"],
    "PBJ":  ["MCD", "SBUX", "YUM", "DPZ"],
    "CARZ": ["TSLA", "F", "GM", "TM"],
    "LUXE": ["CPRI", "RRL", "LULUR", "EL"],
    "XLB":  ["LIN", "APD", "SHW", "CTVA"],
    "LIT":  ["ALB", "SQM", "LAC", "CBAK"],
    "XME":  ["SCCO", "FCX", "RIO", "BHP"],
    "URA":  ["CCJ", "SPRWF", "DNN", "LEU"],
    "XLE":  ["XOM", "CVX", "COP", "MPC"],
    "ICLN": ["PLUG", "SEDG", "ENPH", "RUN"],
    "SLX":  ["X", "SCCO", "CMC", "RS"],
    "ITA":  ["BA", "RTX", "LMT", "GD"],
    "ITB":  ["DHI", "LEN", "PHM", "TOL"],
    "ROBO": ["ISRG", "NDSN", "AXON", "ABB"],
    "FTXR": ["FDX", "UPS", "ODFL", "XPO"],
    "UFO":  ["RKLB", "MAXR", "PAID", "ASTRA"],
    "JETS": ["DAL", "UAL", "AAL", "SWA"],
    "BOAT": ["ZIM", "MATX", "GOGL", "DAC"],
    "IYR":  ["PSA", "SELF", "CCI", "STOR"],
    "PAVE": ["BIP", "KMI", "NEP", "APD"],
    "XHB":  ["DHI", "LEN", "KBH", "LGIH"],
    "INDS": ["ARE", "STWD", "PLD", "WELL"],
    "PBS":  ["CMCSA", "PARA", "FOXO", "LBRDA"],
    "PEJ":  ["DIS", "NFLX", "FOXA", "WBD"],
    "SOCL": ["META", "SNAP", "PINS", "PEP"],
    "XLU":  ["NEE", "D", "SO", "AEP"],
    "DBA":  ["DE", "MON", "AGRO", "ADM"],
    "MSOS": ["CURLF", "GTBIF", "TCNNF", "SNDL"],
    "ESGU": ["AAPL", "MSFT", "NVDA", "GOOGL"],
}

# Deduplicated full signal universe: 54 ETFs + ~216 unique constituent stocks
ALL_SIGNAL_TICKERS: list[str] = list(dict.fromkeys(
    ETF_UNIVERSE +
    [stock for stocks in ETF_CONSTITUENTS.values() for stock in stocks]
))

# Legacy alias — kept for any callers that reference TRACKED_SYMBOLS directly
TRACKED_SYMBOLS = ALL_SIGNAL_TICKERS

_ACTION_ORDER = {"BUY": 0, "HOLD": 1, "SELL": 2}
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


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
        sym = symbol.upper().strip()
        if not _SYMBOL_RE.match(sym):
            return {"date": str(date.today()), "error": "invalid symbol"}
        doc = col.document(sym).get()
        if not doc.exists:
            return {"date": str(date.today()), "symbol": sym, "error": "not found"}
        data = _serialize(doc.to_dict())
        data["symbol"] = sym
        result = {"date": str(date.today()), "symbols": {sym: data}, "total": 1}
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
