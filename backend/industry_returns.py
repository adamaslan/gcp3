"""Industry Returns: reads multi-period ETF return data from shared Firestore industry_cache."""
import logging
from datetime import date

from firestore import db as _db, get_cache, set_cache

logger = logging.getLogger(__name__)

RETURN_PERIODS = ["1w", "2w", "1m", "2m", "3m", "6m", "52w", "2y", "3y", "5y", "10y"]


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


def _rank_by_period(industries: list[dict], period: str) -> list[dict]:
    valid = [i for i in industries if i.get("returns", {}).get(period) is not None]
    return sorted(valid, key=lambda x: x["returns"][period], reverse=True)


async def get_industry_returns() -> dict:
    cache_key = f"industry_returns:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("industry_returns cache hit key=%s", cache_key)
        return cached

    logger.info("industry_returns reading from Firestore industry_cache collection")
    db = _db()
    docs = list(db.collection("industry_cache").stream())

    industries = []
    for d in docs:
        data = _serialize(d.to_dict())
        data.setdefault("industry", d.id)
        industries.append(data)

    # Build rankings for key periods
    rankings: dict[str, list] = {}
    for period in RETURN_PERIODS:
        ranked = _rank_by_period(industries, period)
        if ranked:
            rankings[period] = [
                {"industry": r["industry"], "etf": r.get("etf"), "return": r["returns"][period]}
                for r in ranked
            ]

    # Best/worst for 1m (most actionable)
    month_ranked = _rank_by_period(industries, "1m")
    leaders_1m = month_ranked[:5]
    laggards_1m = month_ranked[-5:]

    # Best/worst for 1w
    week_ranked = _rank_by_period(industries, "1w")
    leaders_1w = week_ranked[:5]
    laggards_1w = week_ranked[-5:]

    # Updated timestamp from most recent doc
    updated = max(
        (i.get("updated", "") for i in industries if i.get("updated")),
        default=str(date.today()),
    )

    result = {
        "date": str(date.today()),
        "updated": updated,
        "total": len(industries),
        "industries": industries,
        "rankings": rankings,
        "leaders_1m": leaders_1m,
        "laggards_1m": laggards_1m,
        "leaders_1w": leaders_1w,
        "laggards_1w": laggards_1w,
        "periods_available": [p for p in RETURN_PERIODS if p in rankings],
    }

    set_cache(cache_key, result, ttl_hours=6)
    return result
