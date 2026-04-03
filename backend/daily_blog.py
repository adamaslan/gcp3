"""Daily Blog Generator: Gemini picks a theme from the 48-topic catalog and writes
a short, engaging finance blog post grounded in that day's live market data.

Runs once per day via Cloud Scheduler (after /refresh/all populates caches).
Cached in Firestore with a to-midnight TTL so only one Gemini call per day.
"""
import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone

import httpx

from firestore import get_cache, set_cache, delete_cache
from morning import get_morning_brief
from sector_rotation import get_sector_rotation
from macro_pulse import get_macro_pulse
from screener import get_screener_data
from news_sentiment import get_news_sentiment

logger = logging.getLogger(__name__)

# ── 48 blog themes organized by tool ────────────────────────────────────────
BLOG_THEMES: list[dict[str, str]] = [
    # Morning Brief (1-4)
    {"id": "morning-alarm-clock", "tool": "morning-brief", "title": "Your Market Alarm Clock", "angle": "Why the first 15 min of data sets the trading day tone"},
    {"id": "morning-four-etfs", "tool": "morning-brief", "title": "Four ETFs That Tell You Everything", "angle": "SPY, QQQ, IWM, DIA as a market health check"},
    {"id": "morning-tone-scoring", "tool": "morning-brief", "title": "Bullish, Bearish, or Just Confused?", "angle": "How tone scoring works under the hood"},
    {"id": "morning-pre-vs-post", "tool": "morning-brief", "title": "Pre-Open vs Post-Open", "angle": "Comparing overnight futures to actual open data"},
    # Industry Tracker (5-8)
    {"id": "industry-50-dashboard", "tool": "industry-tracker", "title": "50 Industries, One Dashboard", "angle": "The case for breadth over depth"},
    {"id": "industry-rotation-surprises", "tool": "industry-tracker", "title": "When Cyber Security Beats Semiconductors", "angle": "Industry rotation surprise stories"},
    {"id": "industry-yfinance-fallback", "tool": "industry-tracker", "title": "The yfinance Fallback", "angle": "Building resilient data pipelines with graceful degradation"},
    {"id": "industry-alpha-vantage", "tool": "industry-tracker", "title": "Alpha Vantage on a Budget", "angle": "Enriching data under a 25-call/day API limit"},
    # Stock Screener (9-12)
    {"id": "screener-40-stocks", "tool": "screener", "title": "40 Stocks Walk Into a Screener", "angle": "How momentum signals filter the noise"},
    {"id": "screener-signal-spectrum", "tool": "screener", "title": "Strong Buy to Strong Sell", "angle": "The signal spectrum explained"},
    {"id": "screener-breadth", "tool": "screener", "title": "Breadth % — The Stat Nobody Talks About", "angle": "Market breadth as a leading indicator"},
    {"id": "screener-ai-disagrees", "tool": "screener", "title": "When the AI Regime Disagrees With You", "angle": "Human vs machine intuition"},
    # Sector Rotation (13-16)
    {"id": "rotation-offense-defense", "tool": "sector-rotation", "title": "Offense vs Defense", "angle": "Reading sector rotation like a playbook"},
    {"id": "rotation-gemini-calls", "tool": "sector-rotation", "title": "Gemini Calls the Shots", "angle": "How LLMs detect rotation patterns"},
    {"id": "rotation-rule-fallback", "tool": "sector-rotation", "title": "Rule-Based Fallback", "angle": "When AI goes dark, math takes over"},
    {"id": "rotation-60-40", "tool": "sector-rotation", "title": "The 60/40 Momentum Score", "angle": "Weighting change % vs intraday position"},
    # Earnings Radar (17-20)
    {"id": "earnings-beat-miss", "tool": "earnings-radar", "title": "Beat or Miss?", "angle": "Why EPS surprise direction matters more than magnitude"},
    {"id": "earnings-6h-cache", "tool": "earnings-radar", "title": "The 6-Hour Cache", "angle": "Timing earnings data freshness for daily traders"},
    {"id": "earnings-20-movers", "tool": "earnings-radar", "title": "20 Companies That Move Markets", "angle": "Which earnings actually matter"},
    {"id": "earnings-ai-outlook", "tool": "earnings-radar", "title": "AI Earnings Outlook", "angle": "Predicting the narrative before the call"},
    # Macro Pulse (21-24)
    {"id": "macro-11-signals", "tool": "macro-pulse", "title": "11 Signals, One Regime", "angle": "Cross-asset regime scoring explained"},
    {"id": "macro-vix-not-fear", "tool": "macro-pulse", "title": "VIX Is Not Fear", "angle": "Debunking the fear gauge myth"},
    {"id": "macro-bonds-gold", "tool": "macro-pulse", "title": "When Bonds and Gold Agree", "angle": "Reading cross-asset confirmation"},
    {"id": "macro-transitional", "tool": "macro-pulse", "title": "Risk-On, Risk-Off, or Just Lost?", "angle": "The Transitional regime"},
    # News Sentiment (25-28)
    {"id": "news-headlines-data", "tool": "news-sentiment", "title": "Headlines as Data", "angle": "Keyword frequency scoring across 4 news categories"},
    {"id": "news-categories-collide", "tool": "news-sentiment", "title": "Crypto News Meets Merger News", "angle": "When categories collide"},
    {"id": "news-sentiment-mirage", "tool": "news-sentiment", "title": "The Sentiment Mirage", "angle": "When positive headlines mask negative price action"},
    {"id": "news-top-movers", "tool": "news-sentiment", "title": "Top Movers and Why They're Moving", "angle": "Connecting sentiment to price"},
    # Portfolio Analyzer (29-32)
    {"id": "portfolio-any-tickers", "tool": "portfolio-analyzer", "title": "Enter Any Tickers", "angle": "Building a personal portfolio health check"},
    {"id": "portfolio-grade", "tool": "portfolio-analyzer", "title": "The A-to-D Diversification Grade", "angle": "What each grade really means"},
    {"id": "portfolio-concentration", "tool": "portfolio-analyzer", "title": "Concentration Risk", "angle": "Why your 5-stock portfolio isn't diversified"},
    {"id": "portfolio-rebalance", "tool": "portfolio-analyzer", "title": "Winners, Losers, and What To Do", "angle": "Portfolio rebalancing signals"},
    # AI Summary (33-36)
    {"id": "ai-five-sources", "tool": "ai-summary", "title": "Five Sources, One Story", "angle": "How Gemini synthesizes conflicting signals"},
    {"id": "ai-daily-narrative", "tool": "ai-summary", "title": "The Daily Market Narrative", "angle": "Why context beats raw numbers"},
    {"id": "ai-leading-lagging", "tool": "ai-summary", "title": "Leading vs Lagging Sectors", "angle": "What the AI picks up that humans miss"},
    {"id": "ai-regime-detection", "tool": "ai-summary", "title": "Regime Detection", "angle": "How tone + data = market regime classification"},
    # Technical Signals (37-40)
    {"id": "signals-confidence", "tool": "technical-signals", "title": "BUY/HOLD/SELL — Ranked by Confidence", "angle": "Reading the signal pipeline output"},
    {"id": "signals-mcp-pipeline", "tool": "technical-signals", "title": "The MCP Pipeline", "angle": "How external analysis flows into Firestore"},
    {"id": "signals-bull-bear", "tool": "technical-signals", "title": "Bull/Bear Counts", "angle": "Aggregate conviction as a market temperature gauge"},
    {"id": "signals-disagree", "tool": "technical-signals", "title": "When Signals Disagree", "angle": "Handling conflicting BUY/SELL on the same day"},
    # Industry Returns (41-44)
    {"id": "returns-multi-tf", "tool": "industry-returns", "title": "1 Week to 10 Years", "angle": "Multi-timeframe returns and why they matter"},
    {"id": "returns-sortable-alpha", "tool": "industry-returns", "title": "Sortable Alpha", "angle": "Finding outperformers across any timeframe"},
    {"id": "returns-etf-dataset", "tool": "industry-returns", "title": "ETF History as a Dataset", "angle": "Permanent storage vs live quotes"},
    {"id": "returns-precompute", "tool": "industry-returns", "title": "The Precompute Trick", "angle": "Turning raw history into ready-to-serve returns"},
    # Market Summary (45-48)
    {"id": "summary-7day", "tool": "market-summary", "title": "7 Days of Conviction", "angle": "Reading the rolling trend window"},
    {"id": "summary-avg-score", "tool": "market-summary", "title": "Average Sentiment Score", "angle": "One number to summarize the week"},
    {"id": "summary-conviction", "tool": "market-summary", "title": "Top Conviction Picks", "angle": "Which stocks the AI keeps flagging"},
    {"id": "summary-regime-trend", "tool": "market-summary", "title": "Regime Trend Direction", "angle": "Is the market shifting or holding steady?"},
]

THEME_COUNT = len(BLOG_THEMES)


def _pick_theme_index(today: date) -> int:
    """Deterministic daily rotation through the 48 themes."""
    ordinal = today.toordinal()
    return ordinal % THEME_COUNT


def _build_blog_prompt(theme: dict[str, str], market_snapshot: dict) -> str:
    """Build the Gemini prompt for today's blog post."""
    return f"""You are a witty, insightful finance blogger who writes for retail investors and trading enthusiasts. Write a short, engaging blog post (400-600 words) on the following theme, grounded in today's live market data.

THEME: "{theme['title']}"
ANGLE: {theme['angle']}
RELATED TOOL: {theme['tool']}
DATE: {date.today()}

TODAY'S MARKET SNAPSHOT:
- Market tone: {market_snapshot.get('tone', 'unknown')}
- Avg index change: {market_snapshot.get('avg_change_pct', 0):+.2f}%
- Macro regime: {market_snapshot.get('macro_regime', 'unknown')}
- Leading sectors: {', '.join(market_snapshot.get('leaders', []))}
- Lagging sectors: {', '.join(market_snapshot.get('laggards', []))}
- Breadth: {market_snapshot.get('breadth_pct', 0):+.1f}%
- News sentiment: {market_snapshot.get('news_sentiment', 'neutral')}
- Top gainers: {', '.join(market_snapshot.get('top_gainers', []))}
- Top losers: {', '.join(market_snapshot.get('top_losers', []))}

INSTRUCTIONS:
1. Open with a hook — a question, bold statement, or analogy that grabs attention.
2. Weave in today's real market data naturally (do NOT just list numbers).
3. Explain the theme's concept clearly for someone new to finance.
4. End with a concise takeaway or "so what" for the reader.
5. Tone: confident, conversational, occasionally playful. No jargon walls.
6. Use short paragraphs. No bullet points — narrative only.
7. Do NOT mention "Gemini", "Finnhub", "GCP", or internal tool names."""


async def _gather_market_snapshot() -> dict:
    """Fetch all 5 live data sources concurrently and extract key fields."""
    morning, rotation, macro, screener, news = await asyncio.gather(
        get_morning_brief(),
        get_sector_rotation(),
        get_macro_pulse(),
        get_screener_data(),
        get_news_sentiment(),
    )
    return {
        "tone": morning.get("market_tone", "unknown"),
        "avg_change_pct": morning.get("avg_change_pct", 0),
        "macro_regime": macro.get("ai_regime", "unknown"),
        "leaders": [r.get("sector", "") for r in rotation.get("leaders", [])],
        "laggards": [r.get("sector", "") for r in rotation.get("laggards", [])],
        "breadth_pct": screener.get("breadth_pct", 0),
        "news_sentiment": news.get("overall_sentiment", "neutral"),
        "top_gainers": [g.get("symbol", "") for g in screener.get("gainers", [])[:5]],
        "top_losers": [l.get("symbol", "") for l in screener.get("losers", [])[:5]],
    }


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


async def refresh_daily_blog() -> dict:
    """Delete today's cache and regenerate. Called by Cloud Scheduler."""
    cache_key = f"daily_blog:{date.today()}"
    delete_cache(cache_key)
    logger.info("daily_blog cache cleared for refresh key=%s", cache_key)
    return await get_daily_blog()


async def get_daily_blog() -> dict:
    """Get today's blog post (cached) or generate a new one via Gemini."""
    today = date.today()
    cache_key = f"daily_blog:{today}"

    if cached := get_cache(cache_key):
        logger.info("daily_blog cache hit key=%s", cache_key)
        return cached

    logger.info("daily_blog cache miss — generating for %s", today)

    theme = BLOG_THEMES[_pick_theme_index(today)]
    snapshot = await _gather_market_snapshot()
    prompt = _build_blog_prompt(theme, snapshot)

    blog_text = await _call_gemini(prompt)
    logger.info("daily_blog: Gemini response received (%d chars)", len(blog_text))

    result = {
        "date": str(today),
        "theme_id": theme["id"],
        "title": theme["title"],
        "tool": theme["tool"],
        "angle": theme["angle"],
        "body": blog_text,
        "market_snapshot": snapshot,
    }

    # Cache until midnight UTC
    now = datetime.now(timezone.utc)
    tomorrow = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
    ttl_hours = max(1, int((tomorrow - now).total_seconds() / 3600))
    set_cache(cache_key, result, ttl_hours=ttl_hours)
    return result
