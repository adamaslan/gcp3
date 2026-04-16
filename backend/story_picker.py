"""Story Picker: Single-pair deep-dive market intelligence article.

Runs daily as Stage B6 in /refresh/bake (after the comprehensive correlation article).
Isolates the single most extreme correlation pair (highest abs score across all 20 pairs)
and generates a focused 300-word article grounded entirely in that one relationship.

Complements daily_correlation (5-pair overview) — this article goes deep on one story.
"""
import logging
import os
from datetime import date, datetime, timedelta, timezone

import httpx

from correlation_article import (
    CorrelationResult,
    _call_gemini,
    _compute_all_correlations,
    _gather_all_sources,
    _generate_title_and_slug,
)
from firestore import delete_cache, get_cache, get_cache_stale_prev, set_cache

logger = logging.getLogger(__name__)


def _pick_extreme_pair(all_pairs: list[CorrelationResult]) -> CorrelationResult | None:
    """Return the single pair with the most extreme score.

    Tiebreak: prefer divergence over agreement (more tension = better story).
    """
    if not all_pairs:
        return None
    return max(
        all_pairs,
        key=lambda p: (
            abs(p.score),
            1 if p.signal == "divergence" else 0,
        ),
    )


def _source_summary(source_key: str, sources: dict) -> str:
    """Extract a human-readable one-line summary of a data source for the prompt."""
    data = sources.get(source_key, {})
    if not data:
        return "data unavailable"

    if source_key == "morning":
        return (
            f"Market tone: {data.get('market_tone', 'unknown')}, "
            f"avg index change: {data.get('avg_change_pct', 0):+.2f}%"
        )
    if source_key == "rotation":
        leaders = [s.get("sector", "") for s in data.get("leaders", [])]
        laggards = [s.get("sector", "") for s in data.get("laggards", [])]
        return f"Leaders: {', '.join(leaders) or 'none'} | Laggards: {', '.join(laggards) or 'none'}"
    if source_key == "macro":
        return f"Regime: {data.get('ai_regime', 'unknown')}"
    if source_key == "screener":
        return (
            f"Breadth: {data.get('breadth_pct', 0):+.1f}%, "
            f"gainers: {len(data.get('gainers', []))}, losers: {len(data.get('losers', []))}"
        )
    if source_key == "news":
        return (
            f"Overall sentiment: {data.get('overall_sentiment', 'neutral')}, "
            f"avg score: {data.get('avg_sentiment_score', 0):+.3f}, "
            f"{data.get('total_articles', 0)} articles"
        )
    if source_key == "earnings":
        beats = len(data.get("beats", []))
        misses = len(data.get("misses", []))
        return f"{beats} earnings beats / {misses} misses"
    if source_key == "industry_returns":
        leaders_1d = data.get("leaders", {}).get("1d", [])
        top = [f"{l.get('industry', '?')} ({l.get('return', 0):+.1f}%)" for l in leaders_1d[:3]]
        return f"Today's top industries: {', '.join(top) or 'n/a'}"
    if source_key == "signals":
        sig = data.get("signal_summary", {})
        return (
            f"Regime: {sig.get('ai_regime', 'unknown')}, "
            f"BUY: {sig.get('buy_count', 0)}, SELL: {sig.get('sell_count', 0)}"
        )
    if source_key == "market_summary":
        return (
            f"7-day trend: {data.get('trend', 'unknown')}, "
            f"sentiment score: {data.get('avg_sentiment_score', 0):+.1f}"
        )
    return str(data)[:120]


# Map pair source_a/source_b strings to sources dict keys
_SOURCE_KEY_MAP = {
    "macro-pulse": "macro",
    "sector-rotation": "rotation",
    "news-sentiment": "news",
    "market-screener": "screener",
    "earnings-radar": "earnings",
    "morning-brief": "morning",
    "industry-returns": "industry_returns",
    "technical-signals": "signals",
    "market-summary": "market_summary",
}


def _build_story_prompt(pair: CorrelationResult, sources: dict) -> str:
    """Build the Gemini prompt for the Story Picker article."""
    source_a_key = _SOURCE_KEY_MAP.get(pair.source_a, pair.source_a.replace("-", "_"))
    source_b_key = _SOURCE_KEY_MAP.get(pair.source_b, pair.source_b.replace("-", "_"))

    source_a_summary = _source_summary(source_a_key, sources)
    source_b_summary = _source_summary(source_b_key, sources)

    signal_description = {
        "divergence": f"strong DIVERGENCE (score: {pair.score:.2f}) — the two sources are pointing in opposite directions",
        "agreement": f"strong AGREEMENT (score: {pair.score:.2f}) — the two sources confirm each other with unusual strength",
        "neutral": f"neutral correlation (score: {pair.score:.2f})",
    }.get(pair.signal, f"score: {pair.score:.2f}")

    return f"""You are a Senior Quantitative Financial Analyst and Viral Content Editor.

Today's market data reveals ONE statistically extreme correlation pair that demands attention.
You must write an article focused ENTIRELY on this single pair. Do not mention other pairs.

DATE: {date.today()}

═══ THE EXTREME PAIR ═══
Pair ID: {pair.pair_id}
Relationship: {pair.source_a} vs {pair.source_b}
Signal: {signal_description}
What this measures: {pair.summary}

═══ WHAT EACH SOURCE SHOWS TODAY ═══
{pair.source_a}: {source_a_summary}
{pair.source_b}: {source_b_summary}

═══ INSTRUCTIONS ═══
Write a market update article of approximately 300 words with this exact structure:

**The Hook (1-2 sentences):**
Open with the specific tension or confirmation this pair reveals today. Name the magnitude — use the score or the direction. Make it feel urgent and specific.

**The Data (2-3 sentences):**
Explain what {pair.source_a} is showing independently, then what {pair.source_b} is showing independently. Be concrete — use the actual data above.

**The Impact (2-3 sentences):**
Explain why THIS specific relationship matters to investors right now.
{"If divergence: what warning does this send? What could resolve it?" if pair.signal == "divergence" else "If agreement: does this confirmation strengthen conviction or is it already priced in?"}
End with one specific thing to watch in the next 24 hours.

TONE RULES:
- Authoritative, sharp, and slightly contrarian
- No "kitchen sink" summaries — stay on this one pair only
- Under 65 characters for the implied headline
- Do NOT mention "Gemini", "Finnhub", "GCP", "Firestore", or internal tool names
- Short paragraphs only. No bullet points."""


async def get_story_article() -> dict:
    """Get today's Story Picker article (cached) or generate via Gemini."""
    today = date.today()
    cache_key = f"daily_story:{today}"

    if cached := get_cache(cache_key):
        logger.info("story_picker cache hit key=%s", cache_key)
        return cached

    logger.info("story_picker cache miss — generating for %s", today)

    # Reuse correlation_article's source gathering and pair computation
    sources = await _gather_all_sources()
    if len(sources) < 3:
        logger.warning(
            "story_picker: only %d sources available, need at least 3 — checking for prior article",
            len(sources),
        )
        stale, stale_as_of = get_cache_stale_prev("daily_story:", cache_key)
        if stale:
            stale_date = stale_as_of or str(today - timedelta(days=1))
            logger.warning("story_picker: serving stale article stale_as_of=%s", stale_date)
            return {**stale, "stale": True, "stale_date": stale_date}
        raise RuntimeError(f"Insufficient data sources ({len(sources)} < 3)")

    all_pairs = _compute_all_correlations(sources)
    extreme_pair = _pick_extreme_pair(all_pairs)
    if extreme_pair is None:
        raise RuntimeError("No correlation pairs could be computed")

    logger.info(
        "story_picker: extreme pair=%s signal=%s score=%.2f",
        extreme_pair.pair_id, extreme_pair.signal, extreme_pair.score,
    )

    prompt = _build_story_prompt(extreme_pair, sources)
    article_text = await _call_gemini(prompt)
    logger.info("story_picker: Gemini response received (%d chars)", len(article_text))

    title, slug = await _generate_title_and_slug([extreme_pair], article_text)

    result = {
        "date": str(today),
        "title": title,
        "slug": slug,
        "body": article_text,
        "extreme_pair": {
            "pair_id": extreme_pair.pair_id,
            "signal": extreme_pair.signal,
            "score": extreme_pair.score,
            "summary": extreme_pair.summary,
            "source_a": extreme_pair.source_a,
            "source_b": extreme_pair.source_b,
        },
        "all_pairs_count": len(all_pairs),
        "stale": False,
    }

    # Cache until midnight UTC
    now = datetime.now(timezone.utc)
    tomorrow = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
    ttl_hours = max(1, int((tomorrow - now).total_seconds() / 3600))
    set_cache(cache_key, result, ttl_hours=ttl_hours)
    return result


async def refresh_story_article() -> dict:
    """Delete today's cache and regenerate. Called by Cloud Scheduler via Stage B6."""
    cache_key = f"daily_story:{date.today()}"
    delete_cache(cache_key)
    logger.info("story_picker cache cleared for refresh key=%s", cache_key)
    return await get_story_article()
