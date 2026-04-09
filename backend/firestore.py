"""Firestore cache client. TTL-based get/set, no auth config needed on Cloud Run."""
from google.cloud import firestore
from datetime import datetime, timedelta, timezone
import os
import time

_db = None

# In-memory cache layer (Phase 2B) — eliminates Firestore reads on hot paths
# Capped at 256 entries; LRU eviction prevents unbounded growth from
# rotating keys like industry_quotes:{minute_bucket}.
_MEM_CACHE_MAX = 256
_MEM_CACHE: dict[str, tuple[float, dict]] = {}


def db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=os.environ["GCP_PROJECT_ID"])
    return _db


def mem_get(key: str, max_age: float = 60.0) -> dict | None:
    """Get from in-memory cache if not stale. Returns None on miss or expiry.

    Args:
        key: Cache key
        max_age: Max age in seconds (default 60s for hot paths like quotes)

    Returns:
        Cached value or None
    """
    entry = _MEM_CACHE.get(key)
    if entry and (time.monotonic() - entry[0]) < max_age:
        return entry[1]
    return None


def mem_set(key: str, value: dict) -> None:
    """Set in-memory cache with current timestamp. Evicts oldest entry when full."""
    if key not in _MEM_CACHE and len(_MEM_CACHE) >= _MEM_CACHE_MAX:
        # FIFO eviction: dicts maintain insertion order (Python 3.7+), O(1)
        del _MEM_CACHE[next(iter(_MEM_CACHE))]
    _MEM_CACHE[key] = (time.monotonic(), value)


def get_cache(key: str) -> dict | None:
    """Get from cache with 3-tier fallback: in-memory → Firestore → None.

    In-memory hits (within 60s) avoid Firestore round-trips on warm instances.
    """
    # Tier 1: In-memory (0ms)
    cached = mem_get(key, max_age=60.0)
    if cached is not None:
        return cached

    # Tier 2: Firestore (50-200ms)
    doc = db().collection("gcp3_cache").document(key).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    expires_at = data.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > datetime.now(timezone.utc):
            value = data.get("value")
            # Populate in-memory for next request
            if value:
                mem_set(key, value)
            return value
    return None


def get_cache_stale(key: str) -> tuple[dict | None, str | None]:
    """Like get_cache but returns stale data instead of None when expired.

    Returns:
        (value, stale_as_of) where stale_as_of is an ISO timestamp if the
        value is stale, None if it is fresh. Both are None if no doc exists.
    """
    doc = db().collection("gcp3_cache").document(key).get()
    if not doc.exists:
        return None, None
    data = doc.to_dict()
    value = data.get("value")
    if value is None:
        return None, None
    expires_at = data.get("expires_at")
    updated_at = data.get("updated_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > datetime.now(timezone.utc):
            return value, None  # fresh
    # Stale — return value with the timestamp it was last written
    stale_as_of = updated_at.isoformat() if updated_at else None
    return value, stale_as_of


def get_cache_stale_prev(prefix: str, exclude_key: str) -> tuple[dict | None, str | None]:
    """Find the most recent previous-day cache entry for a given prefix.

    Uses a document-ID range query instead of list_documents() to avoid a
    full collection scan.  Returns (value, stale_as_of) or (None, None).
    """
    query = (
        db().collection("gcp3_cache")
        .where("__name__", ">=", prefix)
        .where("__name__", "<", prefix + "\uf8ff")
        .order_by("__name__", direction="DESCENDING")
        .limit(2)
    )
    for snap in query.stream():
        if snap.id == exclude_key:
            continue
        data = snap.to_dict()
        value = data.get("value")
        if not value:
            continue
        updated_at = data.get("updated_at")
        stale_as_of = updated_at.isoformat() if updated_at else snap.id.replace(prefix, "")
        return value, stale_as_of
    return None, None


def delete_cache(key: str) -> None:
    db().collection("gcp3_cache").document(key).delete()


def set_cache(key: str, value: dict, ttl_hours: int = 1) -> None:
    """Set cache in both Firestore and in-memory.

    Ensures subsequent reads hit in-memory for 60s without Firestore round-trip.
    """
    now = datetime.now(timezone.utc)
    db().collection("gcp3_cache").document(key).set({
        "value": value,
        "expires_at": now + timedelta(hours=ttl_hours),
        "updated_at": now,
    })
    # Populate in-memory layer for hot path (industry_quotes, screener, etc.)
    mem_set(key, value)


def write_checkpoint(phase: str, status: str, stages_completed: list[str], stages_failed: list[str], extra: dict | None = None) -> None:
    """Write a Fetch/Bake phase checkpoint to Firestore.

    Args:
        phase: "fetch" or "bake"
        status: "fetch_ok" | "fetch_partial" | "fetch_failed" | "bake_ok" | "bake_partial" | "bake_failed"
        stages_completed: List of stage names that completed successfully
        stages_failed: List of stage names that failed
        extra: Optional extra fields to include in checkpoint
    """
    from market_calendar import trading_date

    doc = {
        "trading_date": str(trading_date()),
        "phase": phase,
        "status": status,
        "stages_completed": stages_completed,
        "stages_failed": stages_failed,
        "written_at": datetime.now(timezone.utc),
        **(extra or {}),
    }
    db().collection("gcp3_cache").document(f"refresh_state:{phase}").set(doc)


def read_checkpoint(phase: str) -> dict | None:
    """Read a phase checkpoint. Returns None if missing.

    Args:
        phase: "fetch" or "bake"

    Returns:
        Dict with checkpoint document data, or None if not found
    """
    snap = db().collection("gcp3_cache").document(f"refresh_state:{phase}").get()
    if not snap.exists:
        return None
    return snap.to_dict()
