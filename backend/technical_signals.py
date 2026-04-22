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

# 4 representative constituents per ETF — sourced from docs/tickers3.csv
ETF_CONSTITUENTS: dict[str, list[str]] = {
    "HACK":  ["PANW", "CRWD", "FTNT", "OKTA"],
    "BOTZ":  ["ABB", "FANUY", "KYCCF", "ISRG"],
    "FDN":   ["AMZN", "META", "NFLX", "BKNG"],
    "XLK":   ["MSFT", "AAPL", "NVDA", "AVGO"],
    "VOX":   ["GOOGL", "DIS", "TMUS", "VZ"],
    "IBB":   ["GILD", "AMGN", "VRTX", "REGN"],
    "IGV":   ["CRM", "ORCL", "ADBE", "INTU"],
    "SOXX":  ["AMD", "TXN", "INTC", "MU"],
    "CLOU":  ["AKAM", "DOCN", "ZM", "SNOW"],
    "XPH":   ["ELVN", "OGN", "CORT", "TRVI"],
    "IHF":   ["UNH", "CVS", "HCA", "ELV"],
    "IHI":   ["ABT", "SYK", "BDX", "EW"],
    "XLV":   ["LLY", "JNJ", "ABBV", "MRK"],
    "VHT":   ["PFE", "TMO", "DHR", "BMY"],
    "KBE":   ["JPM", "BAC", "WFC", "C"],
    "KIE":   ["PGR", "TRV", "ALL", "CB"],
    "PFM":   ["COST", "PEP", "LIN", "MCD"],
    "FINX":  ["SQ", "PYPL", "ADYEN", "FIS"],
    "REM":   ["NLY", "AGNC", "STWD", "RITM"],
    "IPAY":  ["MA", "V", "AXP", "DFS"],
    "KRE":   ["NYCB", "ZION", "BPOP", "RF"],
    "XRT":   ["CVNA", "MUSA", "GO", "JWN"],
    "IBUY":  ["FIGS", "LQDT", "SHOP", "ETSY"],
    "XLP":   ["WMT", "PG", "KO", "PM"],
    "ESPO":  ["TCEHY", "NTES", "NTDOY", "EA"],
    "PAWZ":  ["CHWY", "FRPT", "IDXX", "ZTS"],
    "CARZ":  ["TSLA", "F", "GM", "TM"],
    "PBJ":   ["CTVA", "ADM", "KR", "MDLZ"],
    "XLB":   ["NEM", "FCX", "NUE", "SHW"],
    "LIT":   ["RIO", "ALB", "SSDIY", "PCRFY"],
    "XME":   ["UEC", "STLD", "X", "AA"],
    "URA":   ["CCJ", "OKLO", "NXE", "UUUU"],
    "XLE":   ["XOM", "CVX", "COP", "SLB"],
    "ICLN":  ["BE", "FSLR", "NPIFF", "CYPSW"],
    "SLX":   ["BHP", "VALE", "RTNTF", "MT"],
    "ITA":   ["GE", "RTX", "BA", "HWM"],
    "ITB":   ["DHI", "PHM", "LEN", "NVR"],
    "ROBO":  ["HSYCF", "IPGP", "KDXHF", "ZBRA"],
    "FTXR":  ["UNP", "CSX", "NSC", "UPS"],
    "UFO":   ["PL", "VSAT", "RKLB", "SATS"],
    "JETS":  ["DAL", "AAL", "UAL", "LUV"],
    "BOAT":  ["MSLOF", "KARKF", "OROVY", "ZIM"],
    "IYR":   ["WELL", "PLD", "EQIX", "DLR"],
    "PAVE":  ["DE", "ETN", "TT", "EMR"],
    "XHB":   ["MOD", "OC", "WSM", "TOL"],
    "INDS":  ["EXR", "PSA", "SEGXF", "VICI"],
    "PBS":   ["GOOG", "BIDU", "SPOT", "LYV"],
    "PEJ":   ["EXPE", "ABNB", "MAR", "LVS"],
    "SOCL":  ["NHNCF", "KUASF", "PINS", "SNAP"],
    "XLU":   ["NEE", "SO", "DUK", "CEG"],
    "DBA":   ["BG", "TSN", "CF", "MOS"],
    "MSOS":  ["CURLF", "TCNNF", "GTBIF", "VRNOF"],
    "ESGU":  ["HD", "LOW", "ACN", "HON"],
    "QTUM":  ["TER", "COHR", "TSEM", "ONTO"],
}

# Deduplicated full signal universe: 54 ETFs + ~216 unique constituent stocks
ALL_SIGNAL_TICKERS: list[str] = list(dict.fromkeys(
    ETF_UNIVERSE +
    [stock for stocks in ETF_CONSTITUENTS.values() for stock in stocks]
))

# Legacy alias — kept for any callers that reference TRACKED_SYMBOLS directly
TRACKED_SYMBOLS = ALL_SIGNAL_TICKERS

_ACTION_ORDER = {"BUY": 0, "HOLD": 1, "SELL": 2}


def _score_etf(row: dict, rank_1d: int, total: int) -> dict:
    """Derive BUY/HOLD/SELL + signals list from an industry_cache row.

    Each signal carries:
      - signal: short label
      - detail: one-sentence explanation of what this signal means and why it matters
      - strength: BULLISH / BEARISH / NEUTRAL
      - value: the raw number driving the signal
      - weight: how much this signal contributes to the confluence score (1–3)
      - category: momentum / trend / mean_reversion / relative_strength / structure

    Confluence score = weighted sum of (bullish - bearish) / max_possible_weighted_sum,
    scaled to [-1, 1], then rounded to 2 dp.
    """
    returns: dict = row.get("returns") or {}
    r1d  = returns.get("1d")
    r1w  = returns.get("1w")
    r1m  = returns.get("1m")
    r3m  = returns.get("3m")
    r1y  = returns.get("1y")
    r6m  = returns.get("6m")
    high = row.get("52w_high")
    low  = row.get("52w_low")
    name = row.get("industry", row.get("etf", "?"))

    signals: list[dict] = []
    weighted_bull = 0.0
    weighted_bear = 0.0
    max_weight = 0.0

    def _add(signal: str, detail: str, strength: str, value: float, weight: float, category: str) -> None:
        nonlocal weighted_bull, weighted_bear, max_weight
        signals.append({
            "signal": signal,
            "detail": detail,
            "strength": strength,
            "value": value,
            "weight": weight,
            "category": category,
        })
        max_weight += weight
        if strength == "BULLISH":
            weighted_bull += weight
        elif strength == "BEARISH":
            weighted_bear += weight

    # ── Signal 1: Short-term momentum (1d + 1w agreement) — weight 1 ──────────
    if r1d is not None and r1w is not None:
        if r1d > 0 and r1w > 0:
            _add(
                f"Short-term momentum bullish (1d {r1d:+.2f}%, 1w {r1w:+.1f}%)",
                f"{name} is up both today and this week, suggesting near-term buying pressure is sustained rather than a one-day event.",
                "BULLISH", r1d, 1, "momentum",
            )
        elif r1d < 0 and r1w < 0:
            _add(
                f"Short-term momentum bearish (1d {r1d:+.2f}%, 1w {r1w:+.1f}%)",
                f"{name} is down both today and this week, indicating consistent near-term selling pressure across multiple sessions.",
                "BEARISH", r1d, 1, "momentum",
            )
        else:
            _add(
                f"Short-term momentum mixed (1d {r1d:+.2f}%, 1w {r1w:+.1f}%)",
                f"Today's move conflicts with the weekly direction — neither buyers nor sellers have sustained control this week.",
                "NEUTRAL", r1d, 1, "momentum",
            )

    # ── Signal 2: Medium-term momentum (1m + 3m agreement) — weight 2 ─────────
    if r1m is not None and r3m is not None:
        if r1m > 0 and r3m > 2:
            _add(
                f"Medium-term momentum bullish (1m {r1m:+.1f}%, 3m {r3m:+.1f}%)",
                f"Both the 1-month and 3-month returns are positive, confirming that this sector's uptrend has multi-week conviction behind it.",
                "BULLISH", r1m, 2, "momentum",
            )
        elif r1m < 0 and r3m < -2:
            _add(
                f"Medium-term momentum bearish (1m {r1m:+.1f}%, 3m {r3m:+.1f}%)",
                f"Both 1-month and 3-month returns are negative, signaling sustained sector weakness that has persisted across a full quarter.",
                "BEARISH", r1m, 2, "momentum",
            )
        else:
            _add(
                f"Medium-term momentum neutral (1m {r1m:+.1f}%, 3m {r3m:+.1f}%)",
                f"The 1-month and 3-month returns diverge or are near zero, suggesting the sector is in a consolidation or rotation phase.",
                "NEUTRAL", r1m, 2, "momentum",
            )

    # ── Signal 3: Long-term trend (1y) — weight 2 ─────────────────────────────
    if r1y is not None:
        if r1y > 15:
            _add(
                f"Strong long-term uptrend ({r1y:+.1f}% 1y)",
                f"A {r1y:+.1f}% annual return places {name} well above S&P 500 average, indicating structural tailwinds that have persisted for at least a year.",
                "BULLISH", r1y, 2, "trend",
            )
        elif r1y > 0:
            _add(
                f"Moderate long-term uptrend ({r1y:+.1f}% 1y)",
                f"{name} has gained over the past year, but at a pace that suggests steady rather than aggressive sector rotation into this space.",
                "BULLISH", r1y, 1, "trend",
            )
        elif r1y < -15:
            _add(
                f"Strong long-term downtrend ({r1y:+.1f}% 1y)",
                f"A {r1y:+.1f}% annual loss indicates deep structural weakness — investors have been consistently exiting this sector for over a year.",
                "BEARISH", r1y, 2, "trend",
            )
        elif r1y < 0:
            _add(
                f"Moderate long-term downtrend ({r1y:+.1f}% 1y)",
                f"{name} is negative on a 1-year basis, but the moderate loss suggests the sector is drifting lower rather than in full breakdown.",
                "BEARISH", r1y, 1, "trend",
            )
        else:
            _add(
                f"Long-term trend flat ({r1y:+.1f}% 1y)",
                f"Near-zero 1-year return means the sector has neither broken out nor broken down over the past year — range-bound, awaiting a catalyst.",
                "NEUTRAL", r1y, 1, "trend",
            )

    # ── Signal 4: Pullback / counter-trend (1d vs 1y) — weight 2 ─────────────
    if r1d is not None and r1y is not None:
        if r1d < -1 and r1y > 15:
            _add(
                f"Pullback in strong uptrend (today {r1d:+.2f}%, 1y {r1y:+.1f}%)",
                f"Today's dip in an otherwise strong uptrend is a classic mean-reversion setup — the long-term trend remains intact and a single red day rarely breaks it.",
                "BULLISH", r1d, 2, "mean_reversion",
            )
        elif r1d < -0.5 and r1y > 0:
            _add(
                f"Minor pullback in uptrend (today {r1d:+.2f}%, 1y {r1y:+.1f}%)",
                f"Today's decline is modest within a positive annual trend. Not yet a meaningful entry signal, but worth monitoring if weakness continues.",
                "NEUTRAL", r1d, 1, "mean_reversion",
            )
        elif r1d > 1 and r1y < -15:
            _add(
                f"Counter-trend bounce in downtrend (today {r1d:+.2f}%, 1y {r1y:+.1f}%)",
                f"A single-day rally in a structurally weak sector is likely a technical bounce, not a trend reversal. Risk of fading this move is elevated.",
                "BEARISH", r1d, 2, "mean_reversion",
            )

    # ── Signal 5: 52-week range position — weight 3 ───────────────────────────
    if high is not None and low is not None and high > low and r1y is not None:
        range_pct = high - low
        # Estimate current price position using 1y return as proxy
        estimated_pos = 0.5 + (r1y / 200.0)  # rough: 0% 1y ≈ midpoint
        estimated_pos = max(0.0, min(1.0, estimated_pos))
        if r1y > 25 or estimated_pos > 0.75:
            _add(
                f"Trading near 52-week high (range ${low:.0f}–${high:.0f}, {range_pct/high*100:.0f}% spread)",
                f"Strong 1-year performance suggests {name} is near the top of its annual range. Momentum players are rewarded; mean-reversion risk increases.",
                "BULLISH", high, 3, "structure",
            )
        elif r1y < -25 or estimated_pos < 0.25:
            _add(
                f"Trading near 52-week low (range ${low:.0f}–${high:.0f}, {range_pct/high*100:.0f}% spread)",
                f"Deep annual losses place {name} near the bottom of its range. Cheap in price-history terms, but momentum is structurally negative — a value trap risk exists.",
                "BEARISH", low, 3, "structure",
            )

    # ── Signal 6: Relative strength vs 54-ETF universe — weight 2 ────────────
    top_decile = max(1, total // 10)
    top_third  = max(1, total // 3)
    bot_decile = total - top_decile
    bot_third  = total - top_third
    if rank_1d <= top_decile:
        _add(
            f"Top-decile relative strength today (rank #{rank_1d} of {total})",
            f"{name} is in the top 10% of the 54-ETF universe by today's return — institutional rotators are actively moving money into this sector right now.",
            "BULLISH", float(rank_1d), 2, "relative_strength",
        )
    elif rank_1d <= top_third:
        _add(
            f"Above-average relative strength today (rank #{rank_1d} of {total})",
            f"{name} is outperforming the majority of industry ETFs today, suggesting relative buying interest even if the absolute return is modest.",
            "BULLISH", float(rank_1d), 1, "relative_strength",
        )
    elif rank_1d > bot_decile:
        _add(
            f"Bottom-decile relative weakness today (rank #{rank_1d} of {total})",
            f"{name} is in the bottom 10% of the ETF universe — active underperformance at this level often signals sector-specific headwinds, not just market-wide selling.",
            "BEARISH", float(rank_1d), 2, "relative_strength",
        )
    elif rank_1d > bot_third:
        _add(
            f"Below-average relative strength today (rank #{rank_1d} of {total})",
            f"{name} is lagging most industry ETFs today. Persistent relative weakness can precede outright selling as rotators move to stronger sectors.",
            "BEARISH", float(rank_1d), 1, "relative_strength",
        )

    # ── Signal 7: 6-month momentum (if available) — weight 1 ─────────────────
    if r6m is not None:
        if r6m > 10:
            _add(
                f"6-month momentum strong ({r6m:+.1f}%)",
                f"A {r6m:+.1f}% half-year return shows sustained sector strength across two quarters — not just a recent spike.",
                "BULLISH", r6m, 1, "momentum",
            )
        elif r6m < -10:
            _add(
                f"6-month momentum weak ({r6m:+.1f}%)",
                f"A {r6m:+.1f}% six-month loss indicates that weakness has persisted across two full quarters, making recovery harder to sustain.",
                "BEARISH", r6m, 1, "momentum",
            )

    # ── Confluence score ──────────────────────────────────────────────────────
    # Weighted net bullish fraction, scaled to [-1, 1]
    if max_weight > 0:
        raw_score = (weighted_bull - weighted_bear) / max_weight
    else:
        raw_score = 0.0
    confluence_score = round(raw_score, 2)

    # ── Action ────────────────────────────────────────────────────────────────
    bull_sigs = sum(1 for s in signals if s["strength"] == "BULLISH")
    bear_sigs = sum(1 for s in signals if s["strength"] == "BEARISH")

    if confluence_score >= 0.35 and bull_sigs >= 3:
        ai_action = "BUY"
    elif confluence_score <= -0.35 and bear_sigs >= 3:
        ai_action = "SELL"
    else:
        ai_action = "HOLD"

    # ── Summary + outlook ─────────────────────────────────────────────────────
    parts = []
    if r1d is not None: parts.append(f"1d {r1d:+.2f}%")
    if r1m is not None: parts.append(f"1m {r1m:+.1f}%")
    if r1y is not None: parts.append(f"1y {r1y:+.1f}%")
    ai_summary = f"{name} — {', '.join(parts)}" if parts else name

    conf_label = (
        "HIGH" if abs(confluence_score) >= 0.55
        else "MEDIUM" if abs(confluence_score) >= 0.25
        else "LOW"
    )
    if ai_action == "BUY":
        ai_outlook = (
            f"Confluence score {confluence_score:+.2f} ({conf_label}): {bull_sigs} of {len(signals)} signals are bullish "
            f"(weighted {weighted_bull:.0f}/{max_weight:.0f}). Entry case is strongest when today's relative strength "
            f"aligns with the multi-week trend — watch for confirmation on volume."
        )
    elif ai_action == "SELL":
        ai_outlook = (
            f"Confluence score {confluence_score:+.2f} ({conf_label}): {bear_sigs} of {len(signals)} signals are bearish "
            f"(weighted {weighted_bear:.0f}/{max_weight:.0f}). Structural weakness across multiple timeframes — "
            f"risk/reward favors avoiding or reducing exposure until a multi-week trend reversal is confirmed."
        )
    else:
        ai_outlook = (
            f"Confluence score {confluence_score:+.2f} ({conf_label}): signals are split ({bull_sigs} bullish, {bear_sigs} bearish, "
            f"{len(signals) - bull_sigs - bear_sigs} neutral). No dominant directional edge — monitor for a breakout "
            f"above recent highs or breakdown below support before acting."
        )

    return {
        "symbol": row.get("etf", ""),
        "ai_action": ai_action,
        "ai_summary": ai_summary,
        "ai_outlook": ai_outlook,
        "ai_score": confluence_score,
        "ai_confidence": conf_label,
        "confluence_score": confluence_score,
        "confluence_label": conf_label,
        "price": 0.0,
        "signal_count": len(signals),
        "bull_count": bull_sigs,
        "bear_count": bear_sigs,
        "change_pct": r1d,
        "signals": signals,
        "indicators": {"rsi": None, "macd": None, "adx": None},
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

    # Sort: BUY first, then HOLD, then SELL; within each by confluence_score desc
    ranked = sorted(
        scored,
        key=lambda x: (_ACTION_ORDER.get(x["ai_action"], 1), -x.get("confluence_score", 0)),
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
