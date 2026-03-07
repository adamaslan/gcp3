"""AI Market Summary: calls Gemini to synthesize all data sources into a daily brief."""
import asyncio
import logging
import os
from datetime import date

import httpx

from firestore import get_cache, set_cache
from morning import get_morning_brief
from sector_rotation import get_sector_rotation
from macro_pulse import get_macro_pulse
from screener import get_screener_data
from news_sentiment import get_news_sentiment

logger = logging.getLogger(__name__)


def _build_prompt(morning: dict, rotation: dict, macro: dict, screener: dict, news: dict) -> str:
    tone = morning.get("market_tone", "unknown")
    avg_chg = morning.get("avg_change_pct", 0)
    rotation_regime = rotation.get("ai_analysis", "")
    leaders = [r.get("sector", "") for r in rotation.get("leaders", [])]
    laggards = [r.get("sector", "") for r in rotation.get("laggards", [])]
    macro_regime = macro.get("ai_regime", "")
    macro_signals = macro.get("ai_signals", [])
    breadth = screener.get("breadth_pct", 0)
    top_gainers = [g.get("symbol", "") for g in screener.get("gainers", [])[:5]]
    top_losers = [l.get("symbol", "") for l in screener.get("losers", [])[:5]]
    news_sentiment_val = news.get("overall_sentiment", "neutral")
    news_narrative = news.get("ai_narrative", "")

    return f"""You are a senior market analyst. Synthesize the following real-time data into a concise, actionable daily market brief (3-4 paragraphs, no bullet points, conversational tone):

DATE: {date.today()}

MORNING BRIEF:
- Market tone: {tone}
- Major index avg change: {avg_chg:+.2f}%

SECTOR ROTATION:
- Leading sectors: {', '.join(leaders)}
- Lagging sectors: {', '.join(laggards)}
- Analysis: {rotation_regime}

MACRO PULSE:
- Regime: {macro_regime}
- Key signals: {'; '.join(macro_signals[:4])}

STOCK SCREENER:
- Breadth: {breadth:+.1f}% (net buy signals minus sell signals)
- Top gainers: {', '.join(top_gainers)}
- Top losers: {', '.join(top_losers)}

NEWS SENTIMENT:
- Overall: {news_sentiment_val}
- {news_narrative}

Write a professional, confident market brief. Include: (1) overall market character today, (2) what sectors/themes are working, (3) key risks or macro headwinds, (4) a one-sentence tactical takeaway for investors. Do not mention data sources or repeat raw numbers excessively — focus on narrative and insight."""


async def get_ai_summary() -> dict:
    cache_key = f"ai_summary:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("ai_summary cache hit key=%s", cache_key)
        return cached

    logger.info("ai_summary cache miss — gathering all data sources")

    morning, rotation, macro, screener, news = await asyncio.gather(
        get_morning_brief(),
        get_sector_rotation(),
        get_macro_pulse(),
        get_screener_data(),
        get_news_sentiment(),
    )

    prompt = _build_prompt(morning, rotation, macro, screener, news)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("ai_summary: GEMINI_API_KEY not set")
        brief_text = (
            "AI analysis unavailable — GEMINI_API_KEY not configured. "
            "Falling back to data-only summary: "
            f"Markets are {morning.get('market_tone', 'unknown')} with avg move "
            f"{morning.get('avg_change_pct', 0):+.2f}%. "
            f"Macro regime: {macro.get('ai_regime', 'unknown')}."
        )
    else:
        logger.info("ai_summary: calling Gemini gemini-2.0-flash")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            brief_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        logger.info("ai_summary: Gemini response received (%d chars)", len(brief_text))

    result = {
        "date": str(date.today()),
        "brief": brief_text,
        "market_tone": morning.get("market_tone"),
        "macro_regime": macro.get("ai_regime"),
        "leading_sectors": [r.get("sector") for r in rotation.get("leaders", [])],
        "lagging_sectors": [r.get("sector") for r in rotation.get("laggards", [])],
        "breadth_pct": screener.get("breadth_pct"),
        "news_sentiment": news.get("overall_sentiment"),
        "sources": ["morning_brief", "sector_rotation", "macro_pulse", "screener", "news_sentiment"],
    }

    set_cache(cache_key, result, ttl_hours=4)
    return result
