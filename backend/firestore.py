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


def delete_cache(key: str) -> None:
    db().collection("gcp3_cache").document(key).delete()


def set_cache(key: str, value: dict, ttl_hours: int = 1) -> None:
    now = datetime.now(timezone.utc)
    db().collection("gcp3_cache").document(key).set({
        "value": value,
        "expires_at": now + timedelta(hours=ttl_hours),
        "updated_at": now,
    })
