"""Firestore cache client. TTL-based get/set, no auth config needed on Cloud Run."""
from google.cloud import firestore
from datetime import datetime, timedelta, timezone
import os

_db = None


def db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=os.environ["GCP_PROJECT_ID"])
    return _db


def get_cache(key: str) -> dict | None:
    doc = db().collection("gcp3_cache").document(key).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    expires_at = data.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > datetime.now(timezone.utc):
            return data.get("value")
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


def delete_cache(key: str) -> None:
    db().collection("gcp3_cache").document(key).delete()


def set_cache(key: str, value: dict, ttl_hours: int = 1) -> None:
    now = datetime.now(timezone.utc)
    db().collection("gcp3_cache").document(key).set({
        "value": value,
        "expires_at": now + timedelta(hours=ttl_hours),
        "updated_at": now,
    })
