"""Industry Returns: multi-period ETF returns from Firestore industry_cache.

Reads data populated by industry.py._attach_stored_returns (via etf_store).
No API calls — pure Firestore read + in-process ranking.
"""
import logging
from datetime import date

from firestore import db as _db, get_cache, get_cache_stale, set_cache

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
    """Scan gcp3_cache for the most recent industry_returns doc from a prior day.

    Used as a last-resort fallback when today's cache key doesn't exist yet
    (e.g. Firestore outage at the start of a new day before first calculation).
    Returns (value, stale_as_of) or None if no prior entry exists.
    """
    docs = _db().collection("gcp3_cache").list_documents()
    candidates = []
    prefix = "industry_returns:"
    for ref in docs:
        if ref.id.startswith(prefix) and ref.id != f"{prefix}{date.today()}":
            candidates.append(ref.id)
    if not candidates:
        return None
    most_recent_key = max(candidates)  # lexicographic sort works for YYYY-MM-DD
    snap = _db().collection("gcp3_cache").document(most_recent_key).get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    value = data.get("value")
    if not value:
        return None
    updated_at = data.get("updated_at")
    stale_as_of = updated_at.isoformat() if updated_at else most_recent_key.replace(prefix, "")
    return value, stale_as_of


async def get_industry_returns() -> dict:
    cache_key = f"industry_returns:{date.today()}"
    if cached := get_cache(cache_key):
        logger.info("industry_returns cache hit")
        return cached

    try:
        docs = list(_db().collection("industry_cache").stream())
    except Exception as exc:
        logger.warning("industry_returns: industry_cache unreadable (%s) — trying stale cache", exc)
        stale_value, stale_as_of = get_cache_stale(cache_key)
        if stale_value is None:
            prior = _find_most_recent_returns_cache()
            if prior:
                stale_value, stale_as_of = prior
        if stale_value:
            logger.info("industry_returns: serving stale data as_of=%s", stale_as_of)
            return {**stale_value, "stale": True, "stale_as_of": stale_as_of}
        raise

    industries: list[dict] = []
    for d in docs:
        row = _serialize(d.to_dict())
        row.setdefault("industry", d.id)
        row.setdefault("returns", {})
        industries.append(row)

    # Per-period ranked lists (top 5 leaders / laggards each)
    leaders: dict[str, list] = {}
    laggards: dict[str, list] = {}
    for period in RETURN_PERIODS:
        ranked = _rank(industries, period)
        if ranked:
            leaders[period] = [
                {"industry": r["industry"], "etf": r.get("etf"), "return": r["returns"][period]}
                for r in ranked[:5]
            ]
            laggards[period] = [
                {"industry": r["industry"], "etf": r.get("etf"), "return": r["returns"][period]}
                for r in ranked[-5:]
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
    return result
