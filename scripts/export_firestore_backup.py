#!/usr/bin/env python3
"""Point-in-time Firestore → NDJSON export.

Phase 9 of the OpenRouter-migration plan (see
GEMINI_MIGRATION_AUDIT_CORRECTION.md for why this repo mirrors it here rather
than the plan's own copy, and for why this script covers only Phase 9's
"backup" half — the "local" half is superseded by open PR #76's
CACHE_BACKEND=sqlite shim): gcp3 had no backup story at all — prod Firestore
had nothing snapshotting its data anywhere read-only. This is the gcp3-side
counterpart to
nuwrrrld-portal's scripts/backup-to-sqlite.mjs — same posture (read-only,
never overwrites, timestamped output, gitignored), NDJSON instead of SQLite
since Firestore documents are already schemaless JSON and forcing them into
a relational schema (as the portal does for its 30 known Postgres tables)
would need this repo to maintain a Firestore-equivalent schema file that
doesn't exist and isn't wanted — see "Open question" below.

Usage:
    python3 scripts/export_firestore_backup.py
    python3 scripts/export_firestore_backup.py --collections gcp3_cache,other_collection
    python3 scripts/export_firestore_backup.py --out backups/custom-name.ndjson

Requires GCP_PROJECT_ID and real credentials (ADC or GOOGLE_APPLICATION_CREDENTIALS)
pointed at the real project — this reads prod, unlike firestore.py's db()
which can also point at the emulator. Point FIRESTORE_EMULATOR_HOST at a
local emulator instead if you want to export a local run's data (mostly
useful for testing this script itself).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Collections this repo actually writes to, per backend/firestore.py. The
# generic get_generic()/set_generic() helpers there accept an arbitrary
# `collection` argument too, so --collections lets a caller add any others
# discovered later without a code change here.
DEFAULT_COLLECTIONS = ("gcp3_cache",)


def _serialize_value(value):
    """Firestore values that aren't natively JSON-serializable."""
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "latitude") and hasattr(value, "longitude"):  # GeoPoint
        return {"_type": "geopoint", "lat": value.latitude, "lng": value.longitude}
    if hasattr(value, "path"):  # DocumentReference
        return {"_type": "docref", "path": value.path}
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def export_collection(db, collection_name: str, out_fh) -> int:
    count = 0
    for doc in db.collection(collection_name).stream():
        row = {
            "_collection": collection_name,
            "_id": doc.id,
            **_serialize_value(doc.to_dict() or {}),
        }
        out_fh.write(json.dumps(row, default=str) + "\n")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--collections",
        default=",".join(DEFAULT_COLLECTIONS),
        help=f"Comma-separated collection names (default: {','.join(DEFAULT_COLLECTIONS)})",
    )
    parser.add_argument("--out", default=None, help="Output path (default: backups/gcp3-<timestamp>.ndjson)")
    args = parser.parse_args()

    from firestore import db as get_db  # local import: needs GCP_PROJECT_ID set first

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else Path("backups") / f"gcp3-{timestamp}.ndjson"
    if out_path.exists():
        print(f"refusing to overwrite existing file: {out_path}", file=sys.stderr)
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)

    collections = [c.strip() for c in args.collections.split(",") if c.strip()]
    client = get_db()

    total = 0
    tmp_path = out_path.with_suffix(out_path.suffix + ".partial")
    try:
        with open(tmp_path, "w") as fh:
            for name in collections:
                n = export_collection(client, name, fh)
                print(f"  {name}: {n} documents")
                total += n
        tmp_path.rename(out_path)
    except Exception:
        # Partial output is useless and shouldn't linger for a retry to trip over.
        tmp_path.unlink(missing_ok=True)
        raise

    print(f"Wrote {total} documents across {len(collections)} collection(s) to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
