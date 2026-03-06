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
    if expires_at and expires_at.replace(tzinfo=None) > datetime.utcnow():
        return data.get("value")
    return None


def set_cache(key: str, value: dict, ttl_hours: int = 1) -> None:
    db().collection("gcp3_cache").document(key).set({
        "value": value,
        "expires_at": datetime.utcnow() + timedelta(hours=ttl_hours),
        "updated_at": datetime.now(timezone.utc),
    })
