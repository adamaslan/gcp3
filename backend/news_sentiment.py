"""News Sentiment: Finnhub market news + AI sentiment scoring."""
import asyncio
import logging
import os
from datetime import date

import httpx

from firestore import get_cache, set_cache

logger = logging.getLogger(__name__)

CATEGORIES = ["general", "forex", "crypto", "merger"]

POSITIVE_WORDS = {
    "surge", "rally", "gains", "rises", "beats", "exceeds", "record", "strong",
    "upgrade", "buy", "bullish", "growth", "profit", "soars", "jumps", "boosts",
    "recovers", "rebounds", "outperforms", "breakout", "optimistic", "expansion",
}
NEGATIVE_WORDS = {
    "fall", "drops", "plunges", "misses", "weak", "losses", "bearish", "cut",
    "downgrades", "sell", "decline", "crash", "warns", "fears", "recession",
    "layoffs", "default", "bankruptcy", "uncertainty", "contraction", "risks",
    "concern", "slowdown", "headwinds",
}


def _score_headline(headline: str) -> dict:
    words = set(headline.lower().split())
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    if pos > neg:
        sentiment = "positive"
        score = min(1.0, pos * 0.3)
    elif neg > pos:
        sentiment = "negative"
        score = -min(1.0, neg * 0.3)
    else:
        sentiment = "neutral"
        score = 0.0
    return {"sentiment": sentiment, "score": round(score, 2), "pos_hits": pos, "neg_hits": neg}


async def _fetch_news(client: httpx.AsyncClient, category: str) -> list[dict]:
    try:
        r = await client.get(
            "https://finnhub.io/api/v1/news",
            params={"category": category, "token": os.environ["FINNHUB_API_KEY"]},
        )
        r.raise_for_status()
        items = r.json()
        return items[:10] if isinstance(items, list) else []
    except Exception as exc:
        logger.error("news_sentiment fetch failed category=%s: %s", category, exc)
        return []


async def get_news_sentiment() -> dict:
    cache_key = f"news_sentiment:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("news_sentiment cache hit key=%s", cache_key)
        return cached

    logger.info("news_sentiment cache miss — fetching news")

    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(*[_fetch_news(client, cat) for cat in CATEGORIES])

    all_articles = []
    by_category: dict[str, list] = {}

    for category, articles in zip(CATEGORIES, results):
        scored = []
        for a in articles:
            headline = a.get("headline", "")
            sentiment_data = _score_headline(headline)
            scored.append({
                "id": a.get("id"),
                "headline": headline,
                "source": a.get("source"),
                "url": a.get("url"),
                "datetime": a.get("datetime"),
                "category": category,
                **sentiment_data,
            })
        by_category[category] = scored
        all_articles.extend(scored)

    # Aggregate sentiment
    if all_articles:
        avg_score = round(sum(a["score"] for a in all_articles) / len(all_articles), 3)
        pos_count = sum(1 for a in all_articles if a["sentiment"] == "positive")
        neg_count = sum(1 for a in all_articles if a["sentiment"] == "negative")
        neu_count = sum(1 for a in all_articles if a["sentiment"] == "neutral")
        overall_sentiment = "positive" if avg_score > 0.05 else "negative" if avg_score < -0.05 else "neutral"
    else:
        avg_score = 0.0
        pos_count = neg_count = neu_count = 0
        overall_sentiment = "neutral"

    most_positive = sorted(all_articles, key=lambda x: x["score"], reverse=True)[:5]
    most_negative = sorted(all_articles, key=lambda x: x["score"])[:5]

    # AI narrative
    if overall_sentiment == "positive":
        narrative = (
            f"News flow is predominantly positive ({pos_count} positive vs {neg_count} negative articles). "
            "Sentiment tailwind supports risk assets."
        )
    elif overall_sentiment == "negative":
        narrative = (
            f"Negative news dominates ({neg_count} negative vs {pos_count} positive articles). "
            "Sentiment headwind — be selective."
        )
    else:
        narrative = (
            f"Balanced news flow ({pos_count} positive, {neg_count} negative, {neu_count} neutral). "
            "Market narrative is unclear — follow price action."
        )

    result = {
        "date": str(date.today()),
        "total_articles": len(all_articles),
        "by_category": by_category,
        "avg_sentiment_score": avg_score,
        "overall_sentiment": overall_sentiment,
        "positive_count": pos_count,
        "negative_count": neg_count,
        "neutral_count": neu_count,
        "most_positive": most_positive,
        "most_negative": most_negative,
        "ai_narrative": narrative,
    }

    set_cache(cache_key, result, ttl_hours=1)
    return result
