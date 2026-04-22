"""Correlation Article: Cross-source market intelligence grounded in multi-source patterns.

Runs daily after /refresh/all (Stage 8). Detects correlations/divergences between
ALL backend data sources, searches for relevant news, and generates a 600-900 word
article grounded in the strongest patterns.

Data sources (9 total):
  1. morning_brief     — market tone, index moves
  2. sector_rotation   — leading/lagging sectors, offense/defense
  3. macro_pulse       — macro regime, economic signals
  4. screener          — breadth, top gainers/losers
  5. news_sentiment    — overall sentiment, narratives, top movers
  6. earnings_radar    — beats/misses, earnings-driven movers
  7. industry_returns  — 54 ETFs × 13 return periods, leaders/laggards
  8. technical_signals — BUY/HOLD/SELL signals, regime, signal counts
  9. market_summary    — 7-day trend, sentiment history, bullish/bearish lists
"""
import asyncio
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx

from firestore import delete_cache, get_cache, get_cache_stale_prev, set_cache
from morning import get_morning_brief
from sector_rotation import get_sector_rotation
from macro_pulse import get_macro_pulse
from screener import get_screener_data
from news_sentiment import get_news_sentiment
from earnings_radar import get_earnings_radar
from industry_returns import get_industry_returns
from technical_signals import get_technical_signals
from market_summary import get_market_summary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CorrelationResult:
    """Result of comparing two data sources."""
    pair_id: str
    source_a: str
    source_b: str
    score: float  # -1.0 (divergence) to +1.0 (agreement)
    signal: str  # "agreement", "divergence", "neutral"
    summary: str  # one-line description
    data_a: dict  # extracted fields from source A
    data_b: dict  # extracted fields from source B


async def _gather_all_sources() -> dict:
    """Fetch all 9 backend data sources concurrently."""
    results = await asyncio.gather(
        get_morning_brief(),
        get_sector_rotation(),
        get_macro_pulse(),
        get_screener_data(),
        get_news_sentiment(),
        get_earnings_radar(),
        get_industry_returns(),
        get_technical_signals(),
        get_market_summary(),
        return_exceptions=True,
    )

    names = [
        "morning", "rotation", "macro", "screener", "news",
        "earnings", "industry_returns", "signals", "market_summary",
    ]
    sources = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            logger.warning("correlation: source %s failed: %s", name, result)
        else:
            sources[name] = result

    logger.info("correlation: gathered %d/%d sources: %s", len(sources), len(names), list(sources.keys()))
    return sources


def _compute_correlation_score(signal_a: float, signal_b: float) -> float:
    """Compute a graded correlation between two continuous signals in [-1, 1].

    Uses tanh of the product so that:
    - Both signals near ±1 and agreeing → score approaches ±0.76 (tanh(1))
    - Weak signals (near 0) → score compresses toward 0 even if direction matches
    - Hard ±1 inputs are impossible unless the underlying magnitudes actually
      justify them — the caller must pass continuous values, not ±1 flags.

    Returns:
        float in (-1.0, +1.0), never reaching the extremes under realistic inputs.
    """
    return round(math.tanh(signal_a * signal_b * 2.0), 3)


def _normalize_signal(value: float, min_val: float, max_val: float) -> float:
    """Normalize a value to [-1, 1] range."""
    if max_val == min_val:
        return 0.0
    normalized = 2 * (value - min_val) / (max_val - min_val) - 1
    return max(-1.0, min(1.0, normalized))


def _jaccard(set_a: set, set_b: set) -> float:
    """Jaccard similarity in [0, 1]. Empty sets → 0."""
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def _regime_strength(regime_text: str, supporting_val: float, strong_threshold: float) -> float:
    """Return a continuous directional signal for a text regime label.

    Args:
        regime_text: Lower-cased regime string (e.g. 'risk-on', 'bearish').
        supporting_val: A numeric value that should corroborate the label
            (e.g. breadth_pct for a risk-on label, buy_ratio for bullish).
        strong_threshold: Absolute value of supporting_val above which the
            signal is considered strong (scales the output toward ±1).

    Returns:
        Float in [-1, 1] where sign comes from the label and magnitude comes
        from how strongly the supporting_val backs it up.
    """
    if "risk-on" in regime_text or "bullish" in regime_text or "positive" in regime_text:
        direction = 1.0
    elif "risk-off" in regime_text or "bearish" in regime_text or "negative" in regime_text:
        direction = -1.0
    else:
        direction = 0.0

    if direction == 0.0:
        return 0.0

    # Only let supporting_val add magnitude when its sign agrees with direction.
    # A contradicting value (e.g. bullish label but negative breadth) returns the
    # floor signal rather than inflating strength.
    aligned_val = supporting_val if (direction * supporting_val) >= 0 else 0.0
    magnitude = min(abs(aligned_val) / max(strong_threshold, 1e-6), 1.0)
    return direction * (0.3 + 0.7 * magnitude)  # floor of 0.3 when label is set


def _compute_all_correlations(sources: dict) -> list[CorrelationResult]:
    """Compute correlation scores for all 15 tracked pairs."""
    results = []

    # Pair 1: macro vs rotation (regime vs offense/defense)
    if "macro" in sources and "rotation" in sources:
        macro_data = sources["macro"]
        rotation_data = sources["rotation"]

        regime = macro_data.get("ai_regime", "").lower()
        # Use screener breadth as the numeric backer for the regime label
        screener_breadth = sources.get("screener", {}).get("breadth_pct", 0)
        regime_signal = _regime_strength(regime, screener_breadth, strong_threshold=30)

        leaders = rotation_data.get("leaders", [])
        defensive_sectors = {"utilities", "consumer staples", "real estate", "health care"}
        defensive_leader_count = sum(1 for l in leaders if l.get("sector", "").lower() in defensive_sectors)
        offensive_leader_count = len(leaders) - defensive_leader_count
        total_leaders = max(len(leaders), 1)
        # Continuous: +1 = fully offensive, -1 = fully defensive
        offense_signal = (offensive_leader_count - defensive_leader_count) / total_leaders

        score = _compute_correlation_score(regime_signal, offense_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="macro-vs-rotation",
            source_a="macro-pulse",
            source_b="sector-rotation",
            score=score,
            signal=signal_type,
            summary=f"Macro regime {regime} vs sector leadership ({offensive_leader_count} offensive / {defensive_leader_count} defensive leaders)",
            data_a={"regime": regime},
            data_b={"leaders": len(leaders), "offensive": offensive_leader_count, "defensive": defensive_leader_count}
        ))

    # Pair 2: macro vs news
    if "macro" in sources and "news" in sources:
        macro_data = sources["macro"]
        news_data = sources["news"]

        regime = macro_data.get("ai_regime", "").lower()
        screener_breadth = sources.get("screener", {}).get("breadth_pct", 0)
        regime_signal = _regime_strength(regime, screener_breadth, strong_threshold=30)

        sentiment = news_data.get("overall_sentiment", "neutral").lower()
        # Use sentiment score if available, else derive from label
        sentiment_score = news_data.get("sentiment_score", None)
        if sentiment_score is not None:
            sentiment_signal = max(-1.0, min(1.0, float(sentiment_score)))
        else:
            sentiment_signal = _regime_strength(sentiment, abs(screener_breadth), strong_threshold=20)

        score = _compute_correlation_score(regime_signal, sentiment_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="macro-vs-news",
            source_a="macro-pulse",
            source_b="news-sentiment",
            score=score,
            signal=signal_type,
            summary=f"Macro regime {regime} vs news sentiment {sentiment}",
            data_a={"regime": regime},
            data_b={"sentiment": sentiment}
        ))

    # Pair 3: macro vs screener breadth (regime vs 216-stock cross-sector breadth)
    if "macro" in sources and "screener" in sources:
        breadth_pct = sources["screener"].get("breadth_pct", 0)
        regime = sources["macro"].get("ai_regime", "").lower()

        # Continuous regime signal backed by breadth magnitude
        regime_signal = _regime_strength(regime, breadth_pct, strong_threshold=30)
        # Continuous breadth signal: scale ±100% → ±1
        breadth_signal = _normalize_signal(breadth_pct, -100, 100)

        score = _compute_correlation_score(regime_signal, breadth_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="macro-vs-screener",
            source_a="macro-pulse",
            source_b="screener",
            score=score,
            signal=signal_type,
            summary=f"Macro regime {regime} vs breadth {breadth_pct:+.1f}%",
            data_a={"regime": regime},
            data_b={"breadth_pct": breadth_pct}
        ))

    # Pair 4: rotation vs screener
    if "rotation" in sources and "screener" in sources:
        leader_sectors = set(l.get("sector", "").lower() for l in sources["rotation"].get("leaders", []))
        top_gainers = sources["screener"].get("gainers", [])[:5]
        gainer_sectors = set()
        for g in top_gainers:
            # Try to extract sector from gainer if available
            if "sector" in g:
                gainer_sectors.add(g.get("sector", "").lower())

        overlap = len(leader_sectors & gainer_sectors) if leader_sectors else 0
        score = _normalize_signal(overlap, 0, max(len(leader_sectors), len(gainer_sectors), 1))
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.5 else "neutral")

        results.append(CorrelationResult(
            pair_id="rotation-vs-screener",
            source_a="sector-rotation",
            source_b="screener",
            score=score,
            signal=signal_type,
            summary=f"Sector leaders overlapping with top gainers: {overlap} sectors",
            data_a={"leader_sectors": list(leader_sectors)[:3]},
            data_b={"gainer_sectors": list(gainer_sectors)[:3]}
        ))

    # Pair 5: rotation vs news (sector leaders vs news-mentioned sectors)
    if "rotation" in sources and "news" in sources:
        leader_sectors = set(l.get("sector", "").lower() for l in sources["rotation"].get("leaders", []))
        laggard_sectors = set(l.get("sector", "").lower() for l in sources["rotation"].get("laggards", []))
        # Extract sectors mentioned in news movers
        news_movers = sources["news"].get("top_movers", [])[:10]
        mover_symbols = [m.get("symbol", "") for m in news_movers]
        news_sectors = set(m.get("sector", "").lower() for m in news_movers if m.get("sector"))

        leader_overlap = _jaccard(leader_sectors, news_sectors) if news_sectors else 0.0
        laggard_overlap = _jaccard(laggard_sectors, news_sectors) if news_sectors else 0.0
        # Positive if news aligns with leaders, negative if news aligns with laggards
        net = leader_overlap - laggard_overlap
        score = round(max(-1.0, min(1.0, net * 2)), 3)
        signal_type = "agreement" if score > 0.2 else ("divergence" if score < -0.2 else "neutral")

        results.append(CorrelationResult(
            pair_id="rotation-vs-news",
            source_a="sector-rotation",
            source_b="news-sentiment",
            score=score,
            signal=signal_type,
            summary=f"Sector leaders vs news-driven movers (leader overlap: {leader_overlap:.2f}, laggard overlap: {laggard_overlap:.2f})",
            data_a={"leaders": list(leader_sectors)[:3]},
            data_b={"top_movers": mover_symbols[:3]}
        ))

    # Pair 6: screener vs news
    if "screener" in sources and "news" in sources:
        gainers = [g.get("symbol", "") for g in sources["screener"].get("gainers", [])[:5]]
        losers = [l.get("symbol", "") for l in sources["screener"].get("losers", [])[:5]]
        top_movers = [m.get("symbol", "") for m in sources["news"].get("top_movers", [])[:5]]

        gainer_in_news = sum(1 for g in gainers if g in top_movers)
        loser_in_news = sum(1 for l in losers if l in top_movers)

        score = _normalize_signal(gainer_in_news - loser_in_news, -5, 5)
        signal_type = "agreement" if score > 0.3 else "divergence" if score < -0.3 else "neutral"

        results.append(CorrelationResult(
            pair_id="screener-vs-news",
            source_a="screener",
            source_b="news-sentiment",
            score=score,
            signal=signal_type,
            summary=f"Top gainers: {gainer_in_news} in news, Top losers: {loser_in_news} in news",
            data_a={"gainers": gainers[:3], "losers": losers[:3]},
            data_b={"top_movers": top_movers[:3]}
        ))

    # Pair 7: earnings vs screener breadth (beat/miss ratio vs 216-stock breadth)
    if "earnings" in sources and "screener" in sources:
        earnings_data = sources["earnings"]
        beats = len(earnings_data.get("beats", []))
        misses = len(earnings_data.get("misses", []))
        total_earnings = beats + misses or 1
        breadth = sources["screener"].get("breadth_pct", 0)

        # Continuous: net beat ratio in [-1, 1]
        earnings_signal = (beats - misses) / total_earnings
        # Continuous breadth signal
        breadth_signal = _normalize_signal(breadth, -100, 100)

        score = _compute_correlation_score(earnings_signal, breadth_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="earnings-vs-screener",
            source_a="earnings-radar",
            source_b="screener",
            score=score,
            signal=signal_type,
            summary=f"Earnings: {beats} beats vs {misses} misses ({earnings_signal:+.2f} ratio), Breadth: {breadth:+.1f}%",
            data_a={"beats": beats, "misses": misses, "ratio": round(earnings_signal, 2)},
            data_b={"breadth_pct": breadth}
        ))

    # Pair 8: earnings vs news (Jaccard overlap + directional agreement)
    if "earnings" in sources and "news" in sources:
        earnings_data = sources["earnings"]
        beats = earnings_data.get("beats", [])
        misses = earnings_data.get("misses", [])
        news_movers = sources["news"].get("top_movers", [])

        beat_symbols = set(e.get("symbol", "") for e in beats)
        miss_symbols = set(e.get("symbol", "") for e in misses)
        news_symbols = set(n.get("symbol", "") for n in news_movers)

        # Beats appearing in news = agreement; misses appearing in news = divergence
        beat_news_overlap = _jaccard(beat_symbols, news_symbols)
        miss_news_overlap = _jaccard(miss_symbols, news_symbols)
        net_jaccard = beat_news_overlap - miss_news_overlap
        score = round(max(-1.0, min(1.0, net_jaccard * 3)), 3)
        signal_type = "agreement" if score > 0.2 else ("divergence" if score < -0.2 else "neutral")

        results.append(CorrelationResult(
            pair_id="earnings-vs-news",
            source_a="earnings-radar",
            source_b="news-sentiment",
            score=score,
            signal=signal_type,
            summary=f"Earnings/news overlap: {len(beat_symbols & news_symbols)} beats, {len(miss_symbols & news_symbols)} misses in news",
            data_a={"earnings_movers": list(beat_symbols | miss_symbols)[:3]},
            data_b={"news_movers": list(news_symbols)[:3]}
        ))

    # Pair 9: morning vs ETF-breadth (% of 54 industry ETFs positive today)
    if "morning" in sources and "industry_returns" in sources:
        morning_tone = sources["morning"].get("market_tone", "neutral").lower()
        leaders_1d = sources["industry_returns"].get("leaders", {}).get("1d", [])
        laggards_1d = sources["industry_returns"].get("laggards", {}).get("1d", [])
        etf_positive = sum(1 for e in leaders_1d if e.get("return", 0) > 0)
        etf_negative = sum(1 for e in laggards_1d if e.get("return", 0) < 0)
        etf_total = etf_positive + etf_negative or 1
        etf_breadth_pct = round((etf_positive - etf_negative) / etf_total * 100, 1)

        # Tone signal backed by ETF breadth magnitude
        tone_signal = _regime_strength(morning_tone, etf_breadth_pct, strong_threshold=40)
        # Continuous ETF breadth
        breadth_signal = _normalize_signal(etf_breadth_pct, -100, 100)

        score = _compute_correlation_score(tone_signal, breadth_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="morning-vs-etf-breadth",
            source_a="morning-brief",
            source_b="industry-returns",
            score=score,
            signal=signal_type,
            summary=f"Market tone {morning_tone} vs ETF breadth {etf_breadth_pct:+.1f}% ({etf_positive}/{etf_total} ETFs positive)",
            data_a={"tone": morning_tone},
            data_b={"etf_breadth_pct": etf_breadth_pct, "etf_positive": etf_positive, "etf_total": etf_total}
        ))

    # Pair 10: morning vs macro
    if "morning" in sources and "macro" in sources:
        tone = sources["morning"].get("market_tone", "neutral").lower()
        regime = sources["macro"].get("ai_regime", "").lower()
        screener_breadth = sources.get("screener", {}).get("breadth_pct", 0)

        # Both signals backed by screener breadth as corroborating magnitude
        tone_signal = _regime_strength(tone, screener_breadth, strong_threshold=30)
        regime_signal = _regime_strength(regime, screener_breadth, strong_threshold=30)

        score = _compute_correlation_score(tone_signal, regime_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="morning-vs-macro",
            source_a="morning-brief",
            source_b="macro-pulse",
            score=score,
            signal=signal_type,
            summary=f"Market tone {tone} vs macro regime {regime}",
            data_a={"tone": tone},
            data_b={"regime": regime}
        ))

    # ── NEW PAIRS: industry_returns, technical_signals, market_summary ────

    # Pair 11: signals regime vs macro regime
    if "signals" in sources and "macro" in sources:
        sig_summary = sources["signals"].get("signal_summary", {})
        sig_regime = sig_summary.get("ai_regime", "Mixed").lower()
        macro_regime = sources["macro"].get("ai_regime", "").lower()
        buys = sig_summary.get("buy_count", 0)
        sells = sig_summary.get("sell_count", 0)
        total_sig = buys + sells or 1
        screener_breadth = sources.get("screener", {}).get("breadth_pct", 0)

        # Signal regime backed by actual buy/sell ratio
        buy_ratio_pct = (buys - sells) / total_sig * 100
        sig_signal = _regime_strength(sig_regime, buy_ratio_pct, strong_threshold=40)
        # Macro regime backed by screener breadth
        macro_signal = _regime_strength(macro_regime, screener_breadth, strong_threshold=30)

        score = _compute_correlation_score(sig_signal, macro_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="signals-vs-macro",
            source_a="technical-signals",
            source_b="macro-pulse",
            score=score,
            signal=signal_type,
            summary=f"Technical regime {sig_regime} ({buys} BUY/{sells} SELL) vs macro regime {macro_regime}",
            data_a={"regime": sig_regime, "buys": buys, "sells": sells, "buy_ratio_pct": round(buy_ratio_pct, 1)},
            data_b={"regime": macro_regime}
        ))

    # Pair 12: signals BUY/SELL ratio vs ETF-breadth (same 54-ETF universe as signals)
    if "signals" in sources and "industry_returns" in sources:
        sig_summary = sources["signals"].get("signal_summary", {})
        buys = sig_summary.get("buy_count", 0)
        sells = sig_summary.get("sell_count", 0)
        total_sig = buys + sells or 1
        leaders_1d = sources["industry_returns"].get("leaders", {}).get("1d", [])
        laggards_1d = sources["industry_returns"].get("laggards", {}).get("1d", [])
        etf_positive = sum(1 for e in leaders_1d if e.get("return", 0) > 0)
        etf_negative = sum(1 for e in laggards_1d if e.get("return", 0) < 0)
        etf_total = etf_positive + etf_negative or 1
        etf_breadth_pct = round((etf_positive - etf_negative) / etf_total * 100, 1)

        buy_ratio_signal = _normalize_signal(buys - sells, -total_sig, total_sig)
        etf_breadth_signal = _normalize_signal(etf_breadth_pct, -100, 100)

        score = _compute_correlation_score(buy_ratio_signal, etf_breadth_signal)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.5 else "neutral")

        results.append(CorrelationResult(
            pair_id="signals-vs-etf-breadth",
            source_a="technical-signals",
            source_b="industry-returns",
            score=score,
            signal=signal_type,
            summary=f"Signals {buys} BUY / {sells} SELL vs ETF breadth {etf_breadth_pct:+.1f}% ({etf_positive}/{etf_total} ETFs positive)",
            data_a={"buys": buys, "sells": sells},
            data_b={"etf_breadth_pct": etf_breadth_pct, "etf_positive": etf_positive, "etf_total": etf_total}
        ))

    # Pair 13: industry returns leaders vs rotation leaders
    if "industry_returns" in sources and "rotation" in sources:
        ir_leaders_1m = sources["industry_returns"].get("leaders", {}).get("1m", [])
        ir_leader_names = set(l.get("industry", "").lower() for l in ir_leaders_1m[:5])

        rot_leaders = sources["rotation"].get("leaders", [])
        rot_leader_names = set(l.get("sector", "").lower() for l in rot_leaders)

        overlap = len(ir_leader_names & rot_leader_names)
        max_possible = max(len(ir_leader_names), len(rot_leader_names), 1)
        score = _normalize_signal(overlap, 0, max_possible)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="industry-returns-vs-rotation",
            source_a="industry-returns",
            source_b="sector-rotation",
            score=score,
            signal=signal_type,
            summary=f"1-month industry leaders overlap with sector rotation leaders: {overlap}",
            data_a={"leaders_1m": [l.get("industry") for l in ir_leaders_1m[:3]]},
            data_b={"rotation_leaders": [l.get("sector") for l in rot_leaders[:3]]}
        ))

    # Pair 14: industry returns short-term vs long-term (1d vs 1y leaders)
    if "industry_returns" in sources:
        leaders_1d = sources["industry_returns"].get("leaders", {}).get("1d", [])
        leaders_1y = sources["industry_returns"].get("leaders", {}).get("1y", [])

        leaders_1d_names = set(l.get("industry", "").lower() for l in leaders_1d[:5])
        leaders_1y_names = set(l.get("industry", "").lower() for l in leaders_1y[:5])

        overlap = len(leaders_1d_names & leaders_1y_names)
        score = _normalize_signal(overlap, 0, max(len(leaders_1d_names), len(leaders_1y_names), 1))
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.3 else "neutral")

        top_1d = [l.get("industry") for l in leaders_1d[:3]]
        top_1y = [l.get("industry") for l in leaders_1y[:3]]

        results.append(CorrelationResult(
            pair_id="industry-1d-vs-1y",
            source_a="industry-returns-1d",
            source_b="industry-returns-1y",
            score=score,
            signal=signal_type,
            summary=f"Today's leaders ({', '.join(top_1d[:2])}) vs 1-year leaders ({', '.join(top_1y[:2])}): {overlap} overlap",
            data_a={"leaders_1d": top_1d},
            data_b={"leaders_1y": top_1y}
        ))

    # Pair 15: market_summary 7-day trend vs morning tone
    if "market_summary" in sources and "morning" in sources:
        trend = sources["market_summary"].get("trend", "Stable").lower()
        tone = sources["morning"].get("market_tone", "neutral").lower()
        avg_score = float(sources["market_summary"].get("avg_sentiment_score", 0))
        screener_breadth = sources.get("screener", {}).get("breadth_pct", 0)

        # Trend signal backed by 7-day avg sentiment score (typically -1..+1)
        trend_signal = _regime_strength(trend.replace("improv", "bullish").replace("deterior", "bearish"),
                                        avg_score, strong_threshold=0.3)
        # Tone signal backed by today's screener breadth
        tone_signal = _regime_strength(tone, screener_breadth, strong_threshold=30)

        score = _compute_correlation_score(trend_signal, tone_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="trend-vs-morning",
            source_a="market-summary-7d",
            source_b="morning-brief",
            score=score,
            signal=signal_type,
            summary=f"7-day trend {trend} (avg score {avg_score:+.2f}) vs today's tone {tone}",
            data_a={"trend": trend, "avg_score": avg_score},
            data_b={"tone": tone}
        ))

    # Pair 16: market_summary trend vs signals regime
    if "market_summary" in sources and "signals" in sources:
        trend = sources["market_summary"].get("trend", "Stable").lower()
        sig_summary_16 = sources["signals"].get("signal_summary", {})
        sig_regime = sig_summary_16.get("ai_regime", "Mixed").lower()
        avg_score = float(sources["market_summary"].get("avg_sentiment_score", 0))
        buys_16 = sig_summary_16.get("buy_count", 0)
        sells_16 = sig_summary_16.get("sell_count", 0)
        total_16 = buys_16 + sells_16 or 1
        buy_ratio_pct_16 = (buys_16 - sells_16) / total_16 * 100

        trend_signal = _regime_strength(trend.replace("improv", "bullish").replace("deterior", "bearish"),
                                        avg_score * 50, strong_threshold=30)
        sig_signal = _regime_strength(sig_regime, buy_ratio_pct_16, strong_threshold=40)

        score = _compute_correlation_score(trend_signal, sig_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="trend-vs-signals",
            source_a="market-summary-7d",
            source_b="technical-signals",
            score=score,
            signal=signal_type,
            summary=f"7-day trend {trend} (avg score {avg_score:+.2f}) vs signals regime {sig_regime} ({buy_ratio_pct_16:+.0f}% net buy)",
            data_a={"trend": trend, "avg_score": avg_score},
            data_b={"regime": sig_regime, "buy_ratio_pct": round(buy_ratio_pct_16, 1)}
        ))

    # Pair 17: signals vs rotation (BUY sectors vs leading sectors)
    if "signals" in sources and "rotation" in sources:
        buy_signals = sources["signals"].get("buys", [])
        buy_industries = set(b.get("industry", "").lower() for b in buy_signals if b.get("industry"))

        rot_leaders = sources["rotation"].get("leaders", [])
        rot_sectors = set(l.get("sector", "").lower() for l in rot_leaders)

        overlap = len(buy_industries & rot_sectors)
        max_possible = max(len(buy_industries), len(rot_sectors), 1)
        score = _normalize_signal(overlap, 0, max_possible)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="signals-vs-rotation",
            source_a="technical-signals",
            source_b="sector-rotation",
            score=score,
            signal=signal_type,
            summary=f"BUY-signal industries vs rotation leaders: {overlap} overlap",
            data_a={"buy_industries": list(buy_industries)[:3]},
            data_b={"rotation_leaders": list(rot_sectors)[:3]}
        ))

    # Pair 18: signals vs earnings (BUY signals on earnings reporters)
    if "signals" in sources and "earnings" in sources:
        buy_symbols = set(b.get("symbol", "") for b in sources["signals"].get("buys", []))
        sell_symbols = set(s.get("symbol", "") for s in sources["signals"].get("sells", []))
        earnings_data = sources["earnings"]
        earnings_movers = set(
            e.get("symbol", "")
            for e in earnings_data.get("beats", []) + earnings_data.get("misses", [])
        )

        buys_with_earnings = len(buy_symbols & earnings_movers)
        sells_with_earnings = len(sell_symbols & earnings_movers)

        score = _normalize_signal(buys_with_earnings - sells_with_earnings, -3, 3)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="signals-vs-earnings",
            source_a="technical-signals",
            source_b="earnings-radar",
            score=score,
            signal=signal_type,
            summary=f"BUY signals on earnings movers: {buys_with_earnings}, SELL on earnings: {sells_with_earnings}",
            data_a={"buys_with_earnings": buys_with_earnings, "sells_with_earnings": sells_with_earnings},
            data_b={"earnings_movers": list(earnings_movers)[:3]}
        ))

    # Pair 19: industry returns 1m leaders vs news sentiment
    if "industry_returns" in sources and "news" in sources:
        ir_leaders_1m = sources["industry_returns"].get("leaders", {}).get("1m", [])
        ir_laggards_1m = sources["industry_returns"].get("laggards", {}).get("1m", [])
        # Use top-3 average return, not just top-1, to smooth out outliers
        top_returns = [l.get("return", 0) for l in ir_leaders_1m[:3]]
        bottom_returns = [l.get("return", 0) for l in ir_laggards_1m[:3]]
        avg_leader_return = sum(top_returns) / max(len(top_returns), 1)
        avg_laggard_return = sum(bottom_returns) / max(len(bottom_returns), 1)
        spread = avg_leader_return - avg_laggard_return  # wider spread = clearer trend

        sentiment = sources["news"].get("overall_sentiment", "neutral").lower()
        sentiment_score = sources["news"].get("sentiment_score", None)
        if sentiment_score is not None:
            sentiment_signal = max(-1.0, min(1.0, float(sentiment_score)))
        else:
            sentiment_signal = _regime_strength(sentiment, spread, strong_threshold=10)

        # Leader signal: continuous, scaled by avg return magnitude (cap at ±20% = full signal)
        leader_signal = _normalize_signal(avg_leader_return, -20, 20)

        score = _compute_correlation_score(leader_signal, sentiment_signal)
        signal_type = "agreement" if score > 0.3 else ("divergence" if score < -0.3 else "neutral")

        top_leader = ir_leaders_1m[0] if ir_leaders_1m else {}
        results.append(CorrelationResult(
            pair_id="industry-leaders-vs-news",
            source_a="industry-returns",
            source_b="news-sentiment",
            score=score,
            signal=signal_type,
            summary=f"Top industry leaders avg {avg_leader_return:+.1f}% 1m (spread {spread:+.1f}%) vs news {sentiment}",
            data_a={"top_industry": top_leader.get("industry"), "avg_leader_return": round(avg_leader_return, 2), "spread": round(spread, 2)},
            data_b={"sentiment": sentiment}
        ))

    # Pair 20: market_summary bullish list vs signals BUY list
    if "market_summary" in sources and "signals" in sources:
        ms_bullish = set(b.get("symbol", "") if isinstance(b, dict) else str(b)
                         for b in sources["market_summary"].get("top_bullish_today", []))
        sig_buys = set(b.get("symbol", "") for b in sources["signals"].get("buys", []))

        overlap = len(ms_bullish & sig_buys)
        max_possible = max(len(ms_bullish), len(sig_buys), 1)
        score = _normalize_signal(overlap, 0, max_possible)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.3 else "neutral")

        results.append(CorrelationResult(
            pair_id="summary-bullish-vs-signals-buy",
            source_a="market-summary",
            source_b="technical-signals",
            score=score,
            signal=signal_type,
            summary=f"Market summary bullish list vs signals BUY list: {overlap} overlap",
            data_a={"bullish_count": len(ms_bullish)},
            data_b={"buy_count": len(sig_buys)}
        ))

    return results


async def _search_relevant_news(focus_pairs: list[CorrelationResult]) -> list[dict]:
    """Search Finnhub for news relevant to correlation focus pairs."""
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        logger.warning("correlation: FINNHUB_API_KEY not set, skipping news search")
        return []

    # Extract keywords from focus pairs — prefer specific terms over generic source names
    keywords = []
    for pair in focus_pairs:
        if "sector" in str(pair.data_a) or "sector" in str(pair.data_b):
            keywords.append("sector rotation")
        if "regime" in str(pair.data_a) or "regime" in str(pair.data_b):
            keywords.append("macro regime")
        if "earnings" in pair.source_a or "earnings" in pair.source_b:
            keywords.append("earnings")
        if "sentiment" in pair.source_a or "sentiment" in pair.source_b:
            keywords.append("market sentiment")
    # Deduplicate while preserving order
    seen_kw: set[str] = set()
    unique_keywords = [k for k in keywords if not (k in seen_kw or seen_kw.add(k))]  # type: ignore[func-returns-value]
    if not unique_keywords:
        unique_keywords = ["market"]

    news_articles = []
    async with httpx.AsyncClient(timeout=20) as client:
        for keyword in unique_keywords[:3]:  # Limit to 3 searches
            try:
                url = "https://finnhub.io/api/v1/news"
                params = {
                    "category": "general",
                    "minId": 0,
                    "limit": 10,
                    "token": api_key,
                }
                resp = await client.get(url, params=params, timeout=20)
                resp.raise_for_status()

                articles = resp.json()
                # Filter articles whose headline contains the keyword
                keyword_lower = keyword.lower()
                matched = [
                    a for a in articles
                    if keyword_lower in a.get("headline", "").lower()
                    or keyword_lower in a.get("summary", "").lower()
                ]
                for article in (matched or articles)[:3]:
                    news_articles.append({
                        "headline": article.get("headline", ""),
                        "source": article.get("source", ""),
                        "url": article.get("url", ""),
                        "summary": article.get("summary", "")[:200],
                    })
                logger.info(
                    "correlation: news search keyword=%s total=%d matched=%d",
                    keyword, len(articles), len(matched),
                )
            except Exception as e:
                logger.warning("correlation: news search failed for keyword %s: %s", keyword, e)

    # Deduplicate by headline
    seen = set()
    unique_articles = []
    for article in news_articles:
        if article["headline"] not in seen:
            seen.add(article["headline"])
            unique_articles.append(article)

    return unique_articles[:5]


def _build_article_prompt(
    focus_pairs: list[CorrelationResult],
    sources: dict,
    news_articles: list[dict],
) -> str:
    """Build the Gemini prompt for the correlation article using all 9 data sources."""
    focus_section = "\n".join(
        f"  - {p.pair_id}: {p.summary} (signal: {p.signal}, score: {p.score:.2f})"
        for p in focus_pairs[:5]
    )

    # Core market context (original 6 sources)
    ir = sources.get("industry_returns", {})
    leaders_1d_ctx = ir.get("leaders", {}).get("1d", [])
    laggards_1d_ctx = ir.get("laggards", {}).get("1d", [])
    etf_pos_ctx = sum(1 for e in leaders_1d_ctx if e.get("return", 0) > 0)
    etf_neg_ctx = sum(1 for e in laggards_1d_ctx if e.get("return", 0) < 0)
    etf_total_ctx = etf_pos_ctx + etf_neg_ctx or 1
    etf_breadth_ctx = round((etf_pos_ctx - etf_neg_ctx) / etf_total_ctx * 100, 1)

    context_section = f"""
- Market tone: {sources.get('morning', {}).get('market_tone', 'unknown')}
- Macro regime: {sources.get('macro', {}).get('ai_regime', 'unknown')}
- ETF breadth (54 industries): {etf_breadth_ctx:+.1f}% ({etf_pos_ctx}/{etf_total_ctx} ETFs positive today)
- Screener breadth (216-stock cross-sector): {sources.get('screener', {}).get('breadth_pct', 0):+.1f}%
- News sentiment: {sources.get('news', {}).get('overall_sentiment', 'neutral')}
"""

    # Earnings context
    earnings = sources.get("earnings", {})
    beats_list = earnings.get("beats", [])
    misses_list = earnings.get("misses", [])
    beats = len(beats_list)
    misses = len(misses_list)
    earnings_movers = [e.get("symbol", "") for e in (beats_list + misses_list)[:3]]
    context_section += f"- Earnings: {beats} beats / {misses} misses, movers: {', '.join(earnings_movers) or 'none'}\n"

    # Technical signals context (NEW)
    signals = sources.get("signals", {})
    sig_summary = signals.get("signal_summary", {})
    buys = signals.get("buys", [])
    sells = signals.get("sells", [])
    buy_names = [b.get("industry") or b.get("symbol", "") for b in buys[:5]]
    sell_names = [s.get("industry") or s.get("symbol", "") for s in sells[:5]]

    signals_section = f"""
TECHNICAL SIGNALS (54 ETFs across 13 periods):
- Regime: {sig_summary.get('ai_regime', 'unknown')}
- BUY signals: {sig_summary.get('buy_count', 0)} — {', '.join(buy_names) or 'none'}
- SELL signals: {sig_summary.get('sell_count', 0)} — {', '.join(sell_names) or 'none'}
- HOLD signals: {sig_summary.get('hold_count', 0)}
- Total individual signals: {sig_summary.get('total_signals', 0)}
"""

    # Industry returns context (NEW)
    ir = sources.get("industry_returns", {})
    leaders_1d = ir.get("leaders", {}).get("1d", [])
    laggards_1d = ir.get("laggards", {}).get("1d", [])
    leaders_1m = ir.get("leaders", {}).get("1m", [])
    leaders_1y = ir.get("leaders", {}).get("1y", [])
    laggards_1m = ir.get("laggards", {}).get("1m", [])
    laggards_1y = ir.get("laggards", {}).get("1y", [])

    industry_section = f"""
INDUSTRY RETURNS (54 ETFs, {len(ir.get('periods_available', []))} periods available):
- Today's leaders: {', '.join(f"{l.get('industry', '?')} ({l.get('return', 0):+.1f}%)" for l in leaders_1d[:3]) or 'n/a'}
- Today's laggards: {', '.join(f"{l.get('industry', '?')} ({l.get('return', 0):+.1f}%)" for l in laggards_1d[:3]) or 'n/a'}
- 1-month leaders: {', '.join(f"{l.get('industry', '?')} ({l.get('return', 0):+.1f}%)" for l in leaders_1m[:3]) or 'n/a'}
- 1-year leaders: {', '.join(f"{l.get('industry', '?')} ({l.get('return', 0):+.1f}%)" for l in leaders_1y[:3]) or 'n/a'}
- 1-month laggards: {', '.join(f"{l.get('industry', '?')} ({l.get('return', 0):+.1f}%)" for l in laggards_1m[:3]) or 'n/a'}
- 1-year laggards: {', '.join(f"{l.get('industry', '?')} ({l.get('return', 0):+.1f}%)" for l in laggards_1y[:3]) or 'n/a'}
"""

    # Market summary context (NEW)
    ms = sources.get("market_summary", {})
    ms_trend = ms.get("trend", "Stable")
    ms_avg = ms.get("avg_sentiment_score", 0)
    ms_bullish = ms.get("top_bullish_today", [])
    ms_bearish = ms.get("top_bearish_today", [])
    bullish_names = [b.get("symbol", str(b)) if isinstance(b, dict) else str(b) for b in ms_bullish[:3]]
    bearish_names = [b.get("symbol", str(b)) if isinstance(b, dict) else str(b) for b in ms_bearish[:3]]

    summary_section = f"""
MARKET SUMMARY (7-day lookback):
- Trend: {ms_trend}
- Avg sentiment score: {ms_avg:+.1f}
- Today's bullish names: {', '.join(bullish_names) or 'none'}
- Today's bearish names: {', '.join(bearish_names) or 'none'}
- Days analyzed: {ms.get('days_analyzed', 0)}
"""

    # News articles
    news_section = ""
    if news_articles:
        news_section = "\nRELEVANT NEWS:\n"
        news_section += "\n".join(
            f"  - [{a.get('source', 'Unknown')}] {a.get('headline', '')} — {a.get('summary', '')}"
            for a in news_articles[:5]
        )

    return f"""You are a senior financial analyst and writer. Write a 600-900 word market intelligence article that connects multiple data sources to reveal patterns a single-source view would miss.

DATE: {date.today()}

═══ CORRELATION FOCUS (strongest patterns detected) ═══
{focus_section}

═══ FUNDAMENTAL DATA ═══
{context_section}
═══ TECHNICAL SIGNALS ═══
{signals_section}
═══ INDUSTRY PERFORMANCE ═══
{industry_section}
═══ 7-DAY MARKET TREND ═══
{summary_section}
{news_section}

INSTRUCTIONS:
1. Open with the most striking correlation or divergence as a hook — the kind of insight that requires seeing multiple data sources at once.
2. Explain what each data source is showing independently, then what they reveal together. Cross-reference technical signals with industry returns and fundamental data.
3. When technical signals agree with industry returns AND macro regime → emphasize high-conviction setup.
4. When technical signals DIVERGE from fundamentals or news → explain the contrarian opportunity or warning.
5. Use the 7-day trend to provide context: is today confirming or breaking the weekly pattern?
6. Weave in the news articles naturally as supporting evidence or counterpoints.
7. For divergences: explain what could resolve the disagreement and what to watch for.
8. For agreements: explain whether this confirmation strengthens the case or is already priced in.
9. End with 2-3 specific things to watch tomorrow, grounded in which correlations need resolution.
10. Tone: authoritative but accessible. No jargon without explanation.
11. Use short paragraphs. Subheadings welcome for 600+ word pieces.
12. Do NOT mention "Gemini", "Finnhub", "GCP", "Firestore", or internal tool names."""


async def _call_gemini(prompt: str) -> str:
    """Send a prompt to Gemini 2.0 Flash and return the text response."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(url, json=payload, headers={"x-goog-api-key": api_key})
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


async def refresh_correlation_article() -> dict:
    """Delete today's cache and regenerate. Called by Cloud Scheduler."""
    cache_key = f"daily_correlation:{date.today()}"
    delete_cache(cache_key)
    logger.info("correlation_article cache cleared for refresh key=%s", cache_key)
    return await get_correlation_article()


async def get_correlation_article() -> dict:
    """Get today's correlation article (cached) or generate a new one via Gemini."""
    today = date.today()
    cache_key = f"daily_correlation:{today}"

    if cached := get_cache(cache_key):
        logger.info("correlation_article cache hit key=%s", cache_key)
        return cached

    logger.info("correlation_article cache miss — generating for %s", today)

    # Gather all sources
    sources = await _gather_all_sources()
    if len(sources) < 3:
        logger.warning(
            "correlation_article: only %d sources available, need at least 3 — checking for prior article",
            len(sources),
        )
        stale, stale_as_of = get_cache_stale_prev("daily_correlation:", cache_key)
        if stale:
            stale_date = stale_as_of or str(today - timedelta(days=1))
            logger.warning("correlation_article: serving stale article stale_as_of=%s", stale_date)
            return {**stale, "stale": True, "stale_date": stale_date}
        raise RuntimeError(f"Insufficient data sources ({len(sources)} < 3)")

    # Compute correlations across all 20 pairs
    all_pairs = _compute_all_correlations(sources)

    # Select focus pairs: top 3-5 by absolute score, prefer divergence, prefer new sources
    sorted_pairs = sorted(
        all_pairs,
        key=lambda p: (
            abs(p.score),
            -1 if p.signal == "divergence" else 0,
            # Bonus for pairs involving new sources (richer article)
            1 if any(s in p.pair_id for s in ("signals", "industry", "trend", "summary")) else 0,
        ),
        reverse=True,
    )
    focus_pairs = sorted_pairs[:5]

    logger.info(
        "correlation_article: selected %d focus pairs from %d total: %s",
        len(focus_pairs), len(all_pairs),
        [p.pair_id for p in focus_pairs],
    )

    # Search for news
    news_articles = await _search_relevant_news(focus_pairs)
    logger.info("correlation_article: found %d relevant news articles", len(news_articles))

    # Generate article
    prompt = _build_article_prompt(focus_pairs, sources, news_articles)
    article_text = await _call_gemini(prompt)
    logger.info("correlation_article: Gemini response received (%d chars)", len(article_text))

    # Generate catchy title + SEO slug via Gemini (grounded in focus pair signals)
    title, slug = await _generate_title_and_slug(focus_pairs, article_text)

    # Build result
    result = {
        "date": str(today),
        "title": title,
        "slug": slug,
        "body": article_text,
        "focus_pairs": [
            {
                "pair_id": p.pair_id,
                "signal": p.signal,
                "score": p.score,
                "summary": p.summary,
            }
            for p in focus_pairs
        ],
        "sources_used": list(sources.keys()),
        "news_articles": news_articles,
        "correlation_snapshot": {
            "total_pairs": len(all_pairs),
            "agreements": sum(1 for p in all_pairs if p.signal == "agreement"),
            "divergences": sum(1 for p in all_pairs if p.signal == "divergence"),
            "neutral": sum(1 for p in all_pairs if p.signal == "neutral"),
        },
        "signals_regime": sources.get("signals", {}).get("signal_summary", {}).get("ai_regime"),
        "industry_leaders_1m": [
            l.get("industry") for l in
            sources.get("industry_returns", {}).get("leaders", {}).get("1m", [])[:3]
        ],
        "market_trend_7d": sources.get("market_summary", {}).get("trend"),
    }

    # Cache until midnight UTC
    now = datetime.now(timezone.utc)
    tomorrow = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
    ttl_hours = max(1, int((tomorrow - now).total_seconds() / 3600))
    set_cache(cache_key, result, ttl_hours=ttl_hours)
    return result


async def _generate_title_and_slug(
    pairs: list[CorrelationResult], article_text: str
) -> tuple[str, str]:
    """Generate a catchy title and SEO-friendly slug via Gemini.

    Uses the same signal context as the rule-based title (divergence/agreement
    counts, primary pair) but asks Gemini for a more engaging, click-worthy
    headline. Falls back to rule-based title on any error.
    """
    if not pairs:
        fallback = "Market Patterns Across Data Sources"
        return fallback, "market-patterns-across-data-sources"

    primary = pairs[0]
    divergence_count = sum(1 for p in pairs if p.signal == "divergence")
    agreement_count = sum(1 for p in pairs if p.signal == "agreement")

    # Build a concise signal summary as Gemini context (mirrors rule-based logic)
    if divergence_count >= 3:
        signal_context = f"{divergence_count} of {len(pairs)} pairs show divergence — signals and fundamentals are pulling apart"
    elif agreement_count >= 3:
        signal_context = f"{agreement_count} of {len(pairs)} pairs show agreement — technical signals confirm the fundamental story"
    elif primary.signal == "divergence":
        signal_context = f"Primary divergence between {primary.source_a.replace('-', ' ')} and {primary.source_b.replace('-', ' ')}"
    elif primary.signal == "agreement":
        signal_context = f"Primary agreement between {primary.source_a.replace('-', ' ')} and {primary.source_b.replace('-', ' ')}"
    else:
        signal_context = f"Mixed signals across {len(pairs)} data source pairs"

    # Use the opening sentence of the article as additional context
    first_sentence = article_text.split(".")[0].strip() if article_text else ""

    title_prompt = (
        "You are writing a headline for a financial market analysis article.\n\n"
        f"Signal context: {signal_context}\n"
        f"Article opening: {first_sentence}.\n\n"
        "Generate ONE catchy, high-engagement headline (under 80 characters) and ONE "
        "URL-friendly slug (lowercase letters and hyphens only, under 60 characters, no date).\n\n"
        "Rules for the headline:\n"
        "- Must reflect the signal context (divergence vs agreement)\n"
        "- Financial/market language, no clickbait\n"
        "- Under 80 characters\n\n"
        "Respond with exactly two lines:\n"
        "TITLE: <the headline>\n"
        "SLUG: <the-slug>"
    )

    try:
        response = await _call_gemini(title_prompt)
        lines = {
            line.split(":", 1)[0].strip().upper(): line.split(":", 1)[1].strip()
            for line in response.strip().splitlines()
            if ":" in line
        }
        title = lines.get("TITLE", "").strip()
        slug = re.sub(r'[^a-z0-9-]', '', lines.get("SLUG", "").strip().strip("\"'").lower().replace(" ", "-"))
        # Validate: non-empty, reasonable length
        if title and slug and len(title) <= 120 and len(slug) <= 80:
            logger.info("correlation_article: Gemini title=%s slug=%s", title, slug)
            return title, slug
        logger.warning("correlation_article: Gemini title/slug out of spec — falling back")
    except Exception as exc:
        logger.warning("correlation_article: title generation failed: %s — falling back", exc)

    # Fallback to rule-based title
    fallback_title = _generate_title_from_pairs(pairs)
    fallback_slug = fallback_title.lower().replace(":", "").replace("  ", " ").replace(" ", "-")
    return fallback_title, fallback_slug


def _generate_title_from_pairs(pairs: list[CorrelationResult]) -> str:
    """Generate a rule-based article title from the focus correlation pairs.

    Used as fallback when Gemini title generation fails.
    """
    if not pairs:
        return "Market Patterns Across Data Sources"

    primary = pairs[0]
    divergence_count = sum(1 for p in pairs if p.signal == "divergence")
    agreement_count = sum(1 for p in pairs if p.signal == "agreement")

    # Richer titles for multi-source articles
    if divergence_count >= 3:
        return "Markets at a Crossroads: Signals and Fundamentals Pull Apart"
    if agreement_count >= 3:
        return "Consensus Building: Technical Signals Confirm the Fundamental Story"
    if primary.signal == "divergence":
        return f"Divergence Alert: {primary.source_a.replace('-', ' ').title()} vs {primary.source_b.replace('-', ' ').title()}"
    if primary.signal == "agreement":
        return f"{primary.source_a.replace('-', ' ').title()} and {primary.source_b.replace('-', ' ').title()} Align"
    return f"Mixed Signals: What {len(pairs)} Data Sources Reveal Today"
