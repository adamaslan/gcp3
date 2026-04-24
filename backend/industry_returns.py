"""Industry Returns: multi-period ETF returns from Firestore industry_cache.

Reads data populated by industry.py._attach_stored_returns (via etf_store).
No API calls — pure Firestore read + in-process ranking.
"""
import heapq
import logging
from datetime import date

from firestore import db as _db, get_cache, get_cache_stale, get_cache_stale_prev, set_cache

logger = logging.getLogger(__name__)

RETURN_PERIODS = ["1d", "3d", "1w", "2w", "3w", "1m", "3m", "6m", "ytd", "1y", "2y", "5y", "10y"]


def _serialize(doc: dict) -> dict:
    out = {}
    for k, v in doc.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = _serialize(v)
        else:
            out[k] = v
    return out


def _rank(industries: list[dict], period: str) -> list[dict]:
    valid = [i for i in industries if (i.get("returns") or {}).get(period) is not None]
    return sorted(valid, key=lambda x: x["returns"][period], reverse=True)


def _find_most_recent_returns_cache() -> tuple[dict, str] | None:
    """Find the most recent prior-day industry_returns cache doc.

    Uses a document-ID range query instead of list_documents() to avoid a
    full collection scan — same approach as get_cache_stale_prev.
    Returns (value, stale_as_of) or None if no prior entry exists.
    """
    exclude_key = f"industry_returns:{date.today()}"
    return get_cache_stale_prev("industry_returns:", exclude_key) or None


async def get_industry_returns(force: bool = False) -> dict:
    cache_key = f"industry_returns:{date.today()}"
    if not force and (cached := get_cache(cache_key)):
        logger.info("industry_returns: cache_hit key=%s", cache_key)
        return cached

    logger.info("industry_returns: cache_miss key=%s — reading industry_cache", cache_key)
    try:
        docs = list(_db().collection("industry_cache").stream())
    except Exception as exc:
        logger.warning("industry_returns: industry_cache_unreadable error=%s — trying stale cache", exc)
        stale_value, stale_as_of = get_cache_stale(cache_key)
        if stale_value is None:
            prior = _find_most_recent_returns_cache()
            if prior:
                stale_value, stale_as_of = prior
        if stale_value:
            logger.warning("industry_returns: serving_stale_data as_of=%s", stale_as_of)
            return {**stale_value, "stale": True, "stale_as_of": stale_as_of}
        # Today's key doesn't exist yet — fall back to most recent previous day
        prev_value, prev_as_of = get_cache_stale_prev("industry_returns:", cache_key)
        if prev_value:
            logger.warning("industry_returns: serving_prev_day_data as_of=%s", prev_as_of)
            return {**prev_value, "stale": True, "stale_as_of": prev_as_of}
        raise

    industries: list[dict] = []
    for d in docs:
        row = _serialize(d.to_dict())
        row.setdefault("industry", d.id)
        row.setdefault("returns", {})
        industries.append(row)

    # Per-period ranked lists (top 5 leaders / laggards each).
    # heapq is O(N log 5) per period vs O(N log N) full sort — ~3x faster for N=54.
    leaders: dict[str, list] = {}
    laggards: dict[str, list] = {}
    for period in RETURN_PERIODS:
        valid = [
            ((i.get("returns") or {}).get(period), i)
            for i in industries
            if (i.get("returns") or {}).get(period) is not None
        ]
        if not valid:
            continue
        top5 = heapq.nlargest(5, valid, key=lambda x: x[0])
        bot5 = heapq.nsmallest(5, valid, key=lambda x: x[0])
        leaders[period] = [
            {"industry": r["industry"], "etf": r.get("etf"), "return": v}
            for v, r in top5
        ]
        laggards[period] = [
            {"industry": r["industry"], "etf": r.get("etf"), "return": v}
            for v, r in bot5
        ]

    updated = max(
        (i.get("updated", "") for i in industries if i.get("updated")),
        default=str(date.today()),
    )

    # Flatten to list shape the frontend IndustryReturns component expects
    industries_list = [
        {
            "industry": i["industry"],
            "etf": i.get("etf"),
            "returns": i.get("returns", {}),
            "52w_high": i.get("52w_high"),
            "52w_low": i.get("52w_low"),
            "updated": i.get("updated"),
        }
        for i in industries
    ]

    result = {
        "date": str(date.today()),
        "updated": updated,
        "total": len(industries),
        "industries": industries_list,
        "leaders": leaders,
        "laggards": laggards,
        "periods_available": [p for p in RETURN_PERIODS if p in leaders],
    }

    set_cache(cache_key, result, ttl_hours=6)
    logger.info(
        "industry_returns: cache_written key=%s industries=%d updated=%s periods=%s",
        cache_key, len(industries), updated, result["periods_available"],
    )
    return result
