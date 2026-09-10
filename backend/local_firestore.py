"""SQLite-backed Firestore shim for local development (CACHE_BACKEND=sqlite).

Implements the exact — and only the exact — subset of the google-cloud-firestore
client surface that firestore.py and data_client.py use:

    db().collection(name).document(key).get()   -> snapshot(.exists, .to_dict(), .id)
    db().collection(name).document(key).set(dict)
    db().collection(name).document(key).delete()
    db().collection(name).where(f, op, v).where(...).order_by(f, direction=).limit(n).stream()

Datetimes round-trip natively (firestore stores them as native timestamps; get_cache
compares expires_at against datetime.now(tz)), so they are tagged through JSON rather
than stringified. Everything lives in one file DB (LOCAL_CACHE_DB, default
./local_cache.db), one table keyed by (collection, doc_id).

Scale note: this is a dev backend. stream() loads a collection into memory and filters
in Python — fine for a laptop, not for prod (prod uses real Firestore).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import Any, Iterator

_DT_TAG = "__dt__"


def _encode(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return {_DT_TAG: obj.isoformat()}
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_encode(v) for v in obj]
    return obj


def _is_encodable(value: Any) -> bool:
    try:
        json.dumps(_encode(value))
        return True
    except (TypeError, ValueError):
        return False


def _decode(obj: Any) -> Any:
    if isinstance(obj, dict):
        if _DT_TAG in obj and len(obj) == 1:
            return datetime.fromisoformat(obj[_DT_TAG])
        return {k: _decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode(v) for v in obj]
    return obj


class _Snapshot:
    """Mimics firestore DocumentSnapshot for the fields callers actually read."""

    def __init__(self, doc_id: str, data: dict | None) -> None:
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict | None:
        return self._data


class _DocumentRef:
    def __init__(self, store: "LocalFirestoreClient", collection: str, doc_id: str) -> None:
        self._store = store
        self._collection = collection
        self._id = doc_id

    def get(self) -> _Snapshot:
        return _Snapshot(self._id, self._store._read(self._collection, self._id))

    def set(self, data: dict, merge: bool = False) -> None:
        if merge:
            existing = self._store._read(self._collection, self._id) or {}
            # Best-effort per-key: drop values that aren't JSON-encodable (e.g. a
            # firestore.Increment sentinel, which has no local equivalent). Every
            # caller passing such a value is try/except-guarded, so a dropped
            # counter degrades to "not tracked locally" rather than an error.
            merged = dict(existing)
            for key, value in data.items():
                if _is_encodable(value):
                    merged[key] = value
            data = merged
        self._store._write(self._collection, self._id, data)

    def delete(self) -> None:
        self._store._delete(self._collection, self._id)


class _Query:
    """Chainable query supporting only the (field, op, value) / order_by / limit
    combination used by firestore.py::get_cache_stale_prev. `__name__` maps to the
    document id, matching firestore's document-id query semantics."""

    def __init__(self, store: "LocalFirestoreClient", collection: str) -> None:
        self._store = store
        self._collection = collection
        self._filters: list[tuple[str, str, Any]] = []
        self._order_field: str | None = None
        self._descending = False
        self._limit: int | None = None

    def where(self, field: str, op: str, value: Any) -> "_Query":
        self._filters.append((field, op, value))
        return self

    def order_by(self, field: str, direction: str = "ASCENDING") -> "_Query":
        self._order_field = field
        self._descending = str(direction).upper() == "DESCENDING"
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def stream(self) -> Iterator[_Snapshot]:
        rows = self._store._read_collection(self._collection)  # list[(doc_id, data)]

        def field_of(doc_id: str, data: dict, field: str) -> Any:
            return doc_id if field == "__name__" else data.get(field)

        def keep(doc_id: str, data: dict) -> bool:
            for field, op, value in self._filters:
                actual = field_of(doc_id, data, field)
                if op == ">=" and not (actual is not None and actual >= value):
                    return False
                if op == "<" and not (actual is not None and actual < value):
                    return False
                if op == "==" and actual != value:
                    return False
            return True

        filtered = [(doc_id, data) for doc_id, data in rows if keep(doc_id, data)]

        if self._order_field is not None:
            filtered.sort(
                key=lambda r: field_of(r[0], r[1], self._order_field),
                reverse=self._descending,
            )
        if self._limit is not None:
            filtered = filtered[: self._limit]

        for doc_id, data in filtered:
            yield _Snapshot(doc_id, data)


class _CollectionRef:
    def __init__(self, store: "LocalFirestoreClient", collection: str) -> None:
        self._store = store
        self._collection = collection

    def document(self, doc_id: str) -> _DocumentRef:
        return _DocumentRef(self._store, self._collection, doc_id)

    def where(self, field: str, op: str, value: Any) -> _Query:
        return _Query(self._store, self._collection).where(field, op, value)


class LocalFirestoreClient:
    """Drop-in for firestore.Client covering the surface this backend uses."""

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            "  collection TEXT NOT NULL,"
            "  doc_id TEXT NOT NULL,"
            "  data TEXT NOT NULL,"
            "  PRIMARY KEY (collection, doc_id))"
        )
        self._conn.commit()

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, name)

    # --- storage primitives -------------------------------------------------
    def _read(self, collection: str, doc_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM kv WHERE collection=? AND doc_id=?", (collection, doc_id)
            ).fetchone()
        if row is None:
            return None
        return _decode(json.loads(row[0]))

    def _read_collection(self, collection: str) -> list[tuple[str, dict]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc_id, data FROM kv WHERE collection=?", (collection,)
            ).fetchall()
        return [(doc_id, _decode(json.loads(data))) for doc_id, data in rows]

    def _write(self, collection: str, doc_id: str, data: dict) -> None:
        payload = json.dumps(_encode(data))
        with self._lock:
            self._conn.execute(
                "INSERT INTO kv (collection, doc_id, data) VALUES (?, ?, ?) "
                "ON CONFLICT(collection, doc_id) DO UPDATE SET data=excluded.data",
                (collection, doc_id, payload),
            )
            self._conn.commit()

    def _delete(self, collection: str, doc_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM kv WHERE collection=? AND doc_id=?", (collection, doc_id)
            )
            self._conn.commit()
