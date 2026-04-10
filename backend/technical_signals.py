"""Technical Signals: derives BUY/HOLD/SELL signals from industry_cache returns data.

Data source: Firestore industry_cache collection (populated by industry.py + etf_store).
Covers all 54 industry ETFs across 13 return periods — no dependency on gcp-app-w-mcp1.

Signal logic (pure returns-based, no external API calls):
  Momentum  — 1d, 1w, 1m direction agreement
  Trend     — 1y direction
  Pullback  — 1d negative but 1y positive (buyable dip)
  Strength  — 52-week range position
  Breadth   — rank among all 54 ETFs for each period
"""
import logging
from datetime import date

from firestore import get_cache, set_cache
from industry import INDUSTRIES
from industry_returns import get_industry_returns

logger = logging.getLogger(__name__)

# 54 industry ETFs — single source of truth from industry.py
ETF_UNIVERSE: list[str] = [
    etf for sector in INDUSTRIES.values() for etf in sector.values()
]

<<<<<<< HEAD
# 4 primary constituent stocks per ETF (representative holdings)
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
<<<<<<< HEAD
    "IHF":  ["UNH", "ELV", "CVS", "HCA"],
    "IHI":  ["TMO", "ABT", "ISRG", "DXCM"],
    "XLV":  ["LLY", "UNH", "JNJ", "ABBV"],
    "VHT":  ["LLY", "UNH", "JNJ", "TMO"],
    "KBE":  ["JPM", "BAC", "WFC", "GS"],
    "KIE":  ["BRK", "PGR", "TRV", "AIG"],
    "PFM":  ["BLK", "AUM", "BEN", "AMG"],
    "FINX": ["SQ", "PYPL", "COIN", "UPST"],
<<<<<<< HEAD
    "REM":  ["RITM", "AGNC", "NLY", "MFA"],
    "IPAY": ["MA", "V", "AXP", "DFS"],
    "KRE":  ["WAL", "HBAN", "PNC", "FITB"],
    "XRT":  ["AMZN", "TJX", "MCD", "LOW"],
    "IBUY": ["AMZN", "EBAY", "SHOP", "MELI"],
    "XLP":  ["WMT", "PG", "KO", "COST"],
    "ESPO": ["ATVI", "EA", "TTWO", "RBLX"],
<<<<<<< HEAD
    "PAWZ": ["ZTS", "IDXX", "CHWY", "TRUP"],
    "PBJ":  ["MCD", "SBUX", "YUM", "DPZ"],
    "CARZ": ["TSLA", "F", "GM", "TM"],
    "LUXE": ["CPRI", "RL", "LULU", "EL"],
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
<<<<<<< HEAD
    "UFO":  ["RKLB", "LHX", "LMT", "RTX"],
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
<<<<<<< HEAD
    "DBA":  ["DE", "ADM", "TSN", "CTVA"],
    "MSOS": ["CURLF", "GTBIF", "TCNNF", "SNDL"],
    "ESGU": ["AAPL", "MSFT", "NVDA", "GOOGL"],
}

<<<<<<< HEAD
# Deduplicated full signal universe: 54 ETFs + ~216 unique constituent stocks
ALL_SIGNAL_TICKERS: list[str] = list(dict.fromkeys(
    ETF_UNIVERSE +
    [stock for stocks in ETF_CONSTITUENTS.values() for stock in stocks]
))

<<<<<<< HEAD
# Legacy alias — kept for any callers that reference TRACKED_SYMBOLS directly
TRACKED_SYMBOLS = ALL_SIGNAL_TICKERS

_ACTION_ORDER = {"BUY": 0, "HOLD": 1, "SELL": 2}


def _score_etf(row: dict, rank_1d: int, total: int) -> dict:
    """Derive BUY/HOLD/SELL + signals list from an industry_cache row.

    Args:
        row: One industry from get_industry_returns() — has 'returns', '52w_high', '52w_low'
        rank_1d: This ETF's rank by 1d return among all 54 (1 = best)
        total: Total number of ETFs being ranked

    Returns:
        Dict shaped to match the TickerData interface the TechnicalSignals component expects.
    """
    returns: dict = row.get("returns") or {}
    r1d  = returns.get("1d")
    r1w  = returns.get("1w")
    r1m  = returns.get("1m")
    r3m  = returns.get("3m")
    r1y  = returns.get("1y")
    high = row.get("52w_high")
    low  = row.get("52w_low")

    signals: list[dict] = []
    bullish = 0
    bearish = 0

    # Momentum: 1d + 1w + 1m agreement
    if r1d is not None and r1w is not None and r1m is not None:
        if r1d > 0 and r1w > 0 and r1m > 0:
            signals.append({"signal": "Momentum bullish (1d+1w+1m positive)", "strength": "BULLISH", "value": r1m, "category": "momentum"})
            bullish += 1
        elif r1d < 0 and r1w < 0 and r1m < 0:
            signals.append({"signal": "Momentum bearish (1d+1w+1m negative)", "strength": "BEARISH", "value": r1m, "category": "momentum"})
            bearish += 1
        else:
            signals.append({"signal": "Momentum mixed", "strength": "NEUTRAL", "value": r1m, "category": "momentum"})

    # Trend: 1y direction
    if r1y is not None:
        if r1y > 10:
            signals.append({"signal": f"Long-term uptrend ({r1y:+.1f}% 1y)", "strength": "BULLISH", "value": r1y, "category": "trend"})
            bullish += 1
        elif r1y < -10:
            signals.append({"signal": f"Long-term downtrend ({r1y:+.1f}% 1y)", "strength": "BEARISH", "value": r1y, "category": "trend"})
            bearish += 1
        else:
            signals.append({"signal": f"Trend flat ({r1y:+.1f}% 1y)", "strength": "NEUTRAL", "value": r1y, "category": "trend"})

    # Pullback in uptrend (1d red but 1y bullish)
    if r1d is not None and r1y is not None:
        if r1d < 0 and r1y > 10:
            signals.append({"signal": f"Pullback in uptrend ({r1d:+.2f}% today, {r1y:+.1f}% 1y)", "strength": "BULLISH", "value": r1d, "category": "moving_average"})
            bullish += 1
        elif r1d > 0 and r1y < -10:
            signals.append({"signal": f"Counter-trend bounce ({r1d:+.2f}% today, {r1y:+.1f}% 1y)", "strength": "BEARISH", "value": r1d, "category": "moving_average"})
            bearish += 1

    # 52-week range position
    if high and low and high > low:
        pct_of_range = ((high - low) * 0.0 + (high - low)) and (high - low)
        # We don't have current price in industry_cache, use 1y return as proxy:
        # if 1y is strong positive, likely near high
        if r1y is not None:
            if r1y > 20:
                signals.append({"signal": f"Near 52w high (52w range: {low:.0f}–{high:.0f})", "strength": "BULLISH", "value": high, "category": "volume"})
                bullish += 1
            elif r1y < -20:
                signals.append({"signal": f"Near 52w low (52w range: {low:.0f}–{high:.0f})", "strength": "BEARISH", "value": low, "category": "volume"})
                bearish += 1

    # Relative strength: top/bottom third among 54 ETFs by 1d return
    top_third = total // 3
    bottom_third = total - top_third
    if rank_1d <= top_third:
        signals.append({"signal": f"Relative strength: top {top_third} today (rank #{rank_1d})", "strength": "BULLISH", "value": float(rank_1d), "category": "trend_strength"})
        bullish += 1
    elif rank_1d > bottom_third:
        signals.append({"signal": f"Relative weakness: bottom {total - bottom_third} today (rank #{rank_1d})", "strength": "BEARISH", "value": float(rank_1d), "category": "trend_strength"})
        bearish += 1

    # Medium-term momentum: 3m
    if r3m is not None:
        if r3m > 5:
            signals.append({"signal": f"3-month momentum strong ({r3m:+.1f}%)", "strength": "BULLISH", "value": r3m, "category": "momentum"})
            bullish += 1
        elif r3m < -5:
            signals.append({"signal": f"3-month momentum weak ({r3m:+.1f}%)", "strength": "BEARISH", "value": r3m, "category": "momentum"})
            bearish += 1

    # Determine action
    if bullish >= 3 and bullish > bearish * 1.5:
        ai_action = "BUY"
    elif bearish >= 3 and bearish > bullish * 1.5:
        ai_action = "SELL"
    else:
        ai_action = "HOLD"

    # Build summary string
    parts = []
    if r1d is not None:
        parts.append(f"1d {r1d:+.2f}%")
    if r1m is not None:
        parts.append(f"1m {r1m:+.1f}%")
    if r1y is not None:
        parts.append(f"1y {r1y:+.1f}%")
    ai_summary = f"{row.get('industry', row.get('etf', '?'))} — {', '.join(parts)}" if parts else row.get("industry", "")

    outlook_map = {"BUY": "Bullish momentum with trend confirmation", "SELL": "Bearish momentum, trend breakdown", "HOLD": "Mixed signals — monitor for breakout"}

    return {
        "symbol": row.get("etf", ""),
        "ai_action": ai_action,
        "ai_summary": ai_summary,
        "ai_outlook": outlook_map[ai_action],
        "ai_score": round((bullish - bearish) / max(len(signals), 1), 2),
        "ai_confidence": "HIGH" if abs(bullish - bearish) >= 3 else "MEDIUM" if abs(bullish - bearish) >= 1 else "LOW",
        "price": 0.0,  # industry_cache doesn't store price; use /industry-intel for live quotes
        "signal_count": len(signals),
        "change_pct": r1d,
        "signals": signals,
        "indicators": {
            "rsi": None,  # not available from returns data
            "macd": r1m,  # use 1m return as directional proxy
            "adx": r1y,   # use 1y return as trend strength proxy
        },
        "industry": row.get("industry"),
        "returns": returns,
        "52w_high": row.get("52w_high"),
        "52w_low": row.get("52w_low"),
        "updated": row.get("updated"),
    }


async def get_technical_signals(symbol: str | None = None) -> dict:
    """Return BUY/HOLD/SELL signals for all 54 industry ETFs from industry_cache.

    Signals are derived from multi-period return data (no external API calls).
    Source: Firestore industry_cache → get_industry_returns().
    """
    cache_key = f"technical_signals:{symbol or 'all'}:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("technical_signals cache hit key=%s", cache_key)
        return cached

    logger.info("technical_signals building signals from industry_returns symbol=%s", symbol or "all")
    returns_data = await get_industry_returns()
    industries: list[dict] = returns_data.get("industries", [])

    # Rank all ETFs by 1d return for relative strength signal
    with_1d = [(i, (i.get("returns") or {}).get("1d") or 0.0) for i in industries]
    sorted_by_1d = sorted(with_1d, key=lambda x: x[1], reverse=True)
    rank_map: dict[str, int] = {row.get("etf", ""): rank + 1 for rank, (row, _) in enumerate(sorted_by_1d)}
    total = len(industries)

    scored: list[dict] = []
    for row in industries:
        etf = row.get("etf", "")
        if symbol and etf != symbol.upper():
            continue
        rank_1d = rank_map.get(etf, total)
        scored.append(_score_etf(row, rank_1d, total))

    # Sort: BUY first, then HOLD, then SELL; within each by signal_count desc
    ranked = sorted(
        scored,
        key=lambda x: (_ACTION_ORDER.get(x["ai_action"], 1), -x["signal_count"]),
    )
    buys  = [r for r in ranked if r["ai_action"] == "BUY"]
    sells = [r for r in ranked if r["ai_action"] == "SELL"]
    holds = [r for r in ranked if r["ai_action"] == "HOLD"]

    total_signals = sum(r["signal_count"] for r in ranked)
    regime = (
        "Bullish" if len(buys) > len(sells) * 1.5 and len(buys) > total * 0.4
        else "Bearish" if len(sells) > len(buys) * 1.5 and len(sells) > total * 0.4
        else "Mixed"
    )

    if symbol and not ranked:
        result = {"date": str(date.today()), "symbol": symbol.upper(), "error": "not found"}
    elif symbol:
        result = {"date": str(date.today()), "symbols": {ranked[0]["symbol"]: ranked[0]}, "total": 1}
    else:
        result = {
            "date": str(date.today()),
            "updated": returns_data.get("updated"),
            "total": len(ranked),
            "symbols": {r["symbol"]: r for r in ranked},
            "ranked": ranked,
            "buys": buys,
            "sells": sells,
            "holds": holds,
            "signal_summary": {
                "buy_count": len(buys),
                "sell_count": len(sells),
                "hold_count": len(holds),
                "total_signals": total_signals,
                "ai_regime": regime,
            },
        }

    set_cache(cache_key, result, ttl_hours=2)
    logger.info(
        "technical_signals built symbol=%s total=%d buys=%d holds=%d sells=%d total_signals=%d regime=%s",
        symbol or "all", len(ranked), len(buys), len(holds), len(sells), total_signals, regime,
    )
    return result
