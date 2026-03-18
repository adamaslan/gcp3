"""Market Summary: reads daily aggregated AI analysis from shared Firestore summaries collection."""
import logging
from datetime import date

from google.cloud import firestore
from firestore import db as _db, get_cache, set_cache

logger = logging.getLogger(__name__)


def _serialize(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    return obj


async def get_market_summary(days: int = 7) -> dict:
    cache_key = f"market_summary:{date.today()}:d{days}"
    if cached := get_cache(cache_key):
        logger.info("market_summary cache hit key=%s", cache_key)
        return cached

    logger.info("market_summary reading from Firestore summaries collection days=%d", days)
    db = _db()

    docs = list(
        db.collection("summaries")
        .order_by("date", direction=firestore.Query.DESCENDING)
        .limit(days)
        .stream()
    )

    summaries = [_serialize(d.to_dict()) for d in docs]
    latest = summaries[0] if summaries else {}

    # Trend: how bullish/bearish has it been over the period
    daily_scores = []
    for s in summaries:
        bullish = len(s.get("top_bullish", []))
        bearish = len(s.get("top_bearish", []))
        total = s.get("total_analyzed", 1)
        if total:
            score = round((bullish - bearish) / total * 100, 1)
        else:
            score = 0
        daily_scores.append({"date": s.get("date"), "score": score, "bullish": bullish, "bearish": bearish, "total": total})

    avg_score = round(sum(d["score"] for d in daily_scores) / len(daily_scores), 1) if daily_scores else 0
    trend = "Improving" if len(daily_scores) >= 2 and daily_scores[0]["score"] > daily_scores[-1]["score"] else \
            "Deteriorating" if len(daily_scores) >= 2 and daily_scores[0]["score"] < daily_scores[-1]["score"] else "Stable"

    result = {
        "date": str(date.today()),
        "days": days,
        "summaries": summaries,
        "latest": latest,
        "history": summaries,
        "daily_scores": daily_scores,
        "avg_sentiment_score": avg_score,
        "trend": trend,
        "days_analyzed": len(summaries),
        "total_analyzed_today": latest.get("total_analyzed", 0),
        "top_bullish_today": latest.get("top_bullish", []),
        "top_bearish_today": latest.get("top_bearish", []),
        "high_confidence_today": latest.get("high_confidence", []),
    }

    set_cache(cache_key, result, ttl_hours=2)
    return result
