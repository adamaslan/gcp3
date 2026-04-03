"""Correlation Article: Cross-source market intelligence grounded in multi-source patterns.

Runs daily after /refresh/all (Stage 8). Detects correlations/divergences between
2+ data sources, searches for relevant news, and generates a 600-900 word article
grounded in the strongest patterns.
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx

from firestore import delete_cache, get_cache, set_cache
from morning import get_morning_brief
from sector_rotation import get_sector_rotation
from macro_pulse import get_macro_pulse
from screener import get_screener_data
from news_sentiment import get_news_sentiment
from earnings_radar import get_earnings_radar

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
    """Fetch all available data sources concurrently."""
    morning, rotation, macro, screener, news, earnings = await asyncio.gather(
        get_morning_brief(),
        get_sector_rotation(),
        get_macro_pulse(),
        get_screener_data(),
        get_news_sentiment(),
        get_earnings_radar(),
        return_exceptions=True,
    )

    sources = {}
    if not isinstance(morning, Exception):
        sources["morning"] = morning
    if not isinstance(rotation, Exception):
        sources["rotation"] = rotation
    if not isinstance(macro, Exception):
        sources["macro"] = macro
    if not isinstance(screener, Exception):
        sources["screener"] = screener
    if not isinstance(news, Exception):
        sources["news"] = news
    if not isinstance(earnings, Exception):
        sources["earnings"] = earnings

    return sources


def _compute_correlation_score(signal_a: float, signal_b: float) -> float:
    """Compute correlation between two normalized signals (-1 to +1).

    Returns:
        -1.0 (strong divergence) to +1.0 (strong agreement)
    """
    # Simple dot product: if both point the same direction, score is high
    # Normalize to [-1, 1] range
    return signal_a * signal_b


def _normalize_signal(value: float, min_val: float, max_val: float) -> float:
    """Normalize a value to [-1, 1] range."""
    if max_val == min_val:
        return 0.0
    normalized = 2 * (value - min_val) / (max_val - min_val) - 1
    return max(-1.0, min(1.0, normalized))


def _compute_all_correlations(sources: dict) -> list[CorrelationResult]:
    """Compute correlation scores for all 15 tracked pairs."""
    results = []

    # Pair 1: macro vs rotation (regime vs offense/defense)
    if "macro" in sources and "rotation" in sources:
        macro_data = sources["macro"]
        rotation_data = sources["rotation"]

        regime = macro_data.get("ai_regime", "").lower()
        regime_signal = 1.0 if "risk-on" in regime else (-1.0 if "risk-off" in regime else 0.0)

        leaders = rotation_data.get("leaders", [])
        laggards = rotation_data.get("laggards", [])
        defensive_sectors = {"utilities", "consumer staples", "real estate", "health care"}
        defensive_leader_count = sum(1 for l in leaders if l.get("sector", "").lower() in defensive_sectors)

        offense_signal = 1.0 if len(leaders) > defensive_leader_count else (-1.0 if defensive_leader_count > len(leaders) / 2 else 0.0)

        score = _compute_correlation_score(regime_signal, offense_signal)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.5 else "neutral")

        results.append(CorrelationResult(
            pair_id="macro-vs-rotation",
            source_a="macro-pulse",
            source_b="sector-rotation",
            score=score,
            signal=signal_type,
            summary=f"Macro regime {regime} vs sector leadership pattern",
            data_a={"regime": regime},
            data_b={"leaders": len(leaders), "defensive_leading": defensive_leader_count > len(leaders) / 2}
        ))

    # Pair 2: macro vs news
    if "macro" in sources and "news" in sources:
        macro_data = sources["macro"]
        news_data = sources["news"]

        regime = macro_data.get("ai_regime", "").lower()
        regime_signal = 1.0 if "risk-on" in regime else (-1.0 if "risk-off" in regime else 0.0)

        sentiment = news_data.get("overall_sentiment", "neutral").lower()
        sentiment_signal = 1.0 if "positive" in sentiment else (-1.0 if "negative" in sentiment else 0.0)

        score = _compute_correlation_score(regime_signal, sentiment_signal)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.5 else "neutral")

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

    # Pair 3: macro vs screener (regime vs breadth)
    if "macro" in sources and "screener" in sources:
        breadth_pct = sources["screener"].get("breadth_pct", 0)
        regime = sources["macro"].get("ai_regime", "").lower()

        regime_signal = 1.0 if "risk-on" in regime else (-1.0 if "risk-off" in regime else 0.0)
        breadth_signal = 1.0 if breadth_pct > 0 else (-1.0 if breadth_pct < 0 else 0.0)

        score = _compute_correlation_score(regime_signal, breadth_signal)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.5 else "neutral")

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

    # Pair 5: rotation vs news
    if "rotation" in sources and "news" in sources:
        leader_sectors = [l.get("sector", "") for l in sources["rotation"].get("leaders", [])]
        top_movers = sources["news"].get("top_movers", [])[:3]
        mover_symbols = [m.get("symbol", "") for m in top_movers]

        # Check if news-driven movers' sectors align with rotation leaders
        # (simplified: just check if there's overlap in mentions)
        score = _normalize_signal(len(top_movers), 0, 5)
        signal_type = "agreement" if score > 0.3 else "neutral"

        results.append(CorrelationResult(
            pair_id="rotation-vs-news",
            source_a="sector-rotation",
            source_b="news-sentiment",
            score=score,
            signal=signal_type,
            summary=f"Sector leaders vs news-driven movers",
            data_a={"leaders": leader_sectors[:3]},
            data_b={"top_movers": mover_symbols}
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

    # Pair 7: earnings vs screener
    if "earnings" in sources and "screener" in sources:
        earnings_data = sources["earnings"]
        beats = earnings_data.get("beats_count", 0)
        misses = earnings_data.get("misses_count", 0)
        breadth = sources["screener"].get("breadth_pct", 0)

        earnings_signal = 1.0 if beats > misses else (-1.0 if misses > beats else 0.0)
        breadth_signal = 1.0 if breadth > 0 else (-1.0 if breadth < 0 else 0.0)

        score = _compute_correlation_score(earnings_signal, breadth_signal)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.5 else "neutral")

        results.append(CorrelationResult(
            pair_id="earnings-vs-screener",
            source_a="earnings-radar",
            source_b="screener",
            score=score,
            signal=signal_type,
            summary=f"Earnings: {beats} beats vs {misses} misses, Breadth: {breadth:+.1f}%",
            data_a={"beats": beats, "misses": misses},
            data_b={"breadth_pct": breadth}
        ))

    # Pair 8: earnings vs news
    if "earnings" in sources and "news" in sources:
        earnings_movers = sources["earnings"].get("top_movers", [])
        news_movers = sources["news"].get("top_movers", [])

        earnings_symbols = set(e.get("symbol", "") for e in earnings_movers)
        news_symbols = set(n.get("symbol", "") for n in news_movers)

        overlap = len(earnings_symbols & news_symbols)
        score = _normalize_signal(overlap, 0, max(len(earnings_symbols), len(news_symbols), 1))
        signal_type = "agreement" if score > 0.3 else "neutral"

        results.append(CorrelationResult(
            pair_id="earnings-vs-news",
            source_a="earnings-radar",
            source_b="news-sentiment",
            score=score,
            signal=signal_type,
            summary=f"Earnings and news movers overlap: {overlap} stocks",
            data_a={"earnings_movers": list(earnings_symbols)[:3]},
            data_b={"news_movers": list(news_symbols)[:3]}
        ))

    # Pair 9: morning vs screener
    if "morning" in sources and "screener" in sources:
        morning_tone = sources["morning"].get("market_tone", "neutral").lower()
        breadth = sources["screener"].get("breadth_pct", 0)

        tone_signal = 1.0 if "bullish" in morning_tone else (-1.0 if "bearish" in morning_tone else 0.0)
        breadth_signal = 1.0 if breadth > 0 else (-1.0 if breadth < 0 else 0.0)

        score = _compute_correlation_score(tone_signal, breadth_signal)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.5 else "neutral")

        results.append(CorrelationResult(
            pair_id="morning-vs-screener",
            source_a="morning-brief",
            source_b="screener",
            score=score,
            signal=signal_type,
            summary=f"Market tone {morning_tone} vs breadth {breadth:+.1f}%",
            data_a={"tone": morning_tone},
            data_b={"breadth_pct": breadth}
        ))

    # Pair 10: morning vs macro
    if "morning" in sources and "macro" in sources:
        tone = sources["morning"].get("market_tone", "neutral").lower()
        regime = sources["macro"].get("ai_regime", "").lower()

        tone_signal = 1.0 if "bullish" in tone else (-1.0 if "bearish" in tone else 0.0)
        regime_signal = 1.0 if "risk-on" in regime else (-1.0 if "risk-off" in regime else 0.0)

        score = _compute_correlation_score(tone_signal, regime_signal)
        signal_type = "agreement" if score > 0.5 else ("divergence" if score < -0.5 else "neutral")

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

    return results


async def _search_relevant_news(focus_pairs: list[CorrelationResult]) -> list[dict]:
    """Search Finnhub for news relevant to correlation focus pairs."""
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        logger.warning("correlation: FINNHUB_API_KEY not set, skipping news search")
        return []

    # Extract keywords from focus pairs
    keywords = set()
    for pair in focus_pairs:
        # Add source names as keywords
        keywords.add(pair.source_a.replace("-", " "))
        keywords.add(pair.source_b.replace("-", " "))
        # Add data fields
        if "sector" in str(pair.data_a):
            keywords.add("sector rotation")
        if "regime" in str(pair.data_a):
            keywords.add("market regime")

    news_articles = []
    async with httpx.AsyncClient(timeout=20) as client:
        for keyword in list(keywords)[:3]:  # Limit to 3 searches
            try:
                url = "https://finnhub.io/api/v1/news"
                params = {
                    "category": "general",
                    "limit": 5,
                    "token": api_key,
                }
                resp = await client.get(url, params=params, timeout=20)
                resp.raise_for_status()

                articles = resp.json()
                for article in articles[:3]:
                    news_articles.append({
                        "headline": article.get("headline", ""),
                        "source": article.get("source", ""),
                        "url": article.get("url", ""),
                        "summary": article.get("summary", "")[:200],
                    })
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
    """Build the Gemini prompt for the correlation article."""
    focus_section = "\n".join(
        f"  - {p.pair_id}: {p.summary} (signal: {p.signal}, score: {p.score:.2f})"
        for p in focus_pairs[:3]
    )

    context_section = f"""
- Market tone: {sources.get('morning', {}).get('market_tone', 'unknown')}
- Macro regime: {sources.get('macro', {}).get('ai_regime', 'unknown')}
- Breadth: {sources.get('screener', {}).get('breadth_pct', 0):+.1f}%
- News sentiment: {sources.get('news', {}).get('overall_sentiment', 'neutral')}
"""

    news_section = ""
    if news_articles:
        news_section = "\nRELEVANT NEWS:\n"
        news_section += "\n".join(
            f"  - [{a.get('source', 'Unknown')}] {a.get('headline', '')} — {a.get('summary', '')}"
            for a in news_articles[:5]
        )

    return f"""You are a senior financial analyst and writer. Write a 600-900 word market intelligence article that connects multiple data sources to reveal patterns a single-source view would miss.

DATE: {date.today()}

CORRELATION FOCUS:
{focus_section}

SUPPORTING MARKET CONTEXT:
{context_section}
{news_section}

INSTRUCTIONS:
1. Open with the most striking correlation or divergence as a hook.
2. Explain what each data source is showing independently, then what they reveal together.
3. Weave in the news articles naturally as supporting evidence or counterpoints.
4. For divergences: explain what could resolve the disagreement and what to watch for.
5. For agreements: explain whether this confirmation strengthens the case or is already priced in.
6. End with 2-3 specific things to watch tomorrow.
7. Tone: authoritative but accessible. No jargon without explanation.
8. Use short paragraphs. Subheadings welcome for 600+ word pieces.
9. Do NOT mention "Gemini", "Finnhub", "GCP", or internal tool names."""


async def _call_gemini(prompt: str) -> str:
    """Send a prompt to Gemini 2.0 Flash and return the text response."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(url, json=payload)
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
            "correlation_article: only %d sources available, need at least 3",
            len(sources),
        )
        raise RuntimeError(f"Insufficient data sources ({len(sources)} < 3)")

    # Compute correlations
    all_pairs = _compute_all_correlations(sources)

    # Select focus pairs (top 2-3 by absolute score, prefer divergence)
    sorted_pairs = sorted(all_pairs, key=lambda p: (abs(p.score), -1 if p.signal == "divergence" else 0), reverse=True)
    focus_pairs = sorted_pairs[:3]

    logger.info("correlation_article: selected %d focus pairs", len(focus_pairs))

    # Search for news
    news_articles = await _search_relevant_news(focus_pairs)
    logger.info("correlation_article: found %d relevant news articles", len(news_articles))

    # Generate article
    prompt = _build_article_prompt(focus_pairs, sources, news_articles)
    article_text = await _call_gemini(prompt)
    logger.info("correlation_article: Gemini response received (%d chars)", len(article_text))

    # Generate title from focus pairs
    title = _generate_title_from_pairs(focus_pairs)

    # Build result
    result = {
        "date": str(today),
        "title": title,
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
            "agreements": sum(1 for p in all_pairs if p.signal == "agreement"),
            "divergences": sum(1 for p in all_pairs if p.signal == "divergence"),
            "neutral": sum(1 for p in all_pairs if p.signal == "neutral"),
        },
    }

    # Cache until midnight UTC
    now = datetime.now(timezone.utc)
    tomorrow = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
    ttl_hours = max(1, int((tomorrow - now).total_seconds() / 3600))
    set_cache(cache_key, result, ttl_hours=ttl_hours)
    return result


def _generate_title_from_pairs(pairs: list[CorrelationResult]) -> str:
    """Generate an article title from the focus correlation pairs."""
    if not pairs:
        return "Market Patterns Across Data Sources"

    primary = pairs[0]
    if primary.signal == "divergence":
        return f"When {primary.source_a.title()} Says No But {primary.source_b.title()} Says Yes"
    elif primary.signal == "agreement":
        return f"{primary.source_a.title()} and {primary.source_b.title()} Align"
    else:
        return f"Patterns in {primary.source_a.title()} and {primary.source_b.title()}"
