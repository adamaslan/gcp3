"""Firestore cache client — TTL-based get/set, collection: gcp3_backend2_cache."""
import os
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

_db = None
_COLLECTION = "gcp3_backend2_cache"


def db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=os.environ["GCP_PROJECT_ID"])
    return _db


def get_cache(key: str) -> dict | None:
    doc = db().collection(_COLLECTION).document(key).get()
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


def set_cache(key: str, value: dict, ttl_hours: int = 1) -> None:
    now = datetime.now(timezone.utc)
    db().collection(_COLLECTION).document(key).set({
        "value": value,
        "expires_at": now + timedelta(hours=ttl_hours),
        "updated_at": now,
    })
