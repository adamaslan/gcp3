"""Archive-before-purge: writes expiring gcp3_cache docs to the GCS Parquet
data lake before they are deleted by /admin/purge-cache.

Implements docs/data-monetization-25-tips.md Tips 1, 2, 4, 5:
- Tip 1: never TTL history away — archive every expiring doc first.
- Tip 2: append-only Parquet in GCS, partitioned by date.
- Tip 4: stamp schema_version so historical rows are attributable to an engine.
- Tip 5: stamp as_of (best-effort, falls back to computed_at) alongside computed_at.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)

DATA_LAKE_BUCKET = os.environ.get("NWF_DATA_LAKE_BUCKET", "nwf-data-lake")
ARCHIVE_SCHEMA_VERSION = "1"


def _row_from_doc(doc_id: str, data: dict) -> dict:
    """Flatten a gcp3_cache document into one archive row.

    `value` is stored as-is (JSON-serializable dict); everything else is
    metadata needed for point-in-time correctness and provenance.
    """
    updated_at = data.get("updated_at")
    computed_at = updated_at if isinstance(updated_at, datetime) else datetime.now(timezone.utc)
    value = data.get("value") or {}
    as_of = value.get("as_of") or value.get("date") or computed_at.isoformat()
    # as_of can arrive as a string, a date, or a datetime depending on which
    # producer wrote the source doc. PyArrow infers a Parquet column's type
    # per file, so mixed types across archive files (all sharing one GCS
    # prefix / BigQuery external table) produce mismatched physical schemas.
    # Normalize to one ISO-8601 string before it ever reaches the DataFrame.
    if isinstance(as_of, (datetime, date)):
        as_of = as_of.isoformat()
    elif not isinstance(as_of, str):
        as_of = str(as_of)

    return {
        "key": doc_id,
        "as_of": as_of,
        "computed_at": computed_at.isoformat(),
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "data_quality_score": value.get("data_quality_score"),
        "value_json": _json_dumps(value),
    }


def _json_dumps(value: dict) -> str:
    import json
    return json.dumps(value, default=str)


class ArchiveError(Exception):
    """Raised when archive_expired_docs cannot confirm docs reached the data
    lake. Callers MUST NOT delete the corresponding Firestore documents when
    this is raised — deleting anyway is exactly the "silently deleting the
    sellable history" outcome docs/data-monetization-25-tips.md Tip 1 exists
    to prevent."""


def archive_expired_docs(docs: list[tuple[str, dict]], source: str = "gcp3_cache") -> int:
    """Write expiring cache docs to gs://<bucket>/<source>/dt=YYYY-MM-DD/*.parquet.

    Args:
        docs: list of (doc_id, doc_dict) pairs about to be purged.
        source: archive prefix, one per Firestore collection archived.

    Returns:
        Number of rows written — 0 only when `docs` was empty.

    Raises:
        ArchiveError: on any failure writing to the data lake. This used to
        swallow every failure and return 0 so "a data-lake outage never
        blocks the purge" — but purge_expired_cache never checked the
        return value before deleting, so a failed archive was followed by
        permanent deletion anyway, defeating archive-before-purge entirely.
        Raising lets the caller skip deletion for exactly the batch that
        failed to archive, instead of silently losing it.
    """
    if not docs:
        return 0

    buf_path = None
    try:
        from google.cloud import storage  # type: ignore

        rows = [_row_from_doc(doc_id, data) for doc_id, data in docs]
        df = pd.DataFrame(rows)

        dt = date.today().isoformat()
        filename = f"{uuid.uuid4().hex}.parquet"
        blob_path = f"{source}/dt={dt}/{filename}"

        buf_path = f"/tmp/{filename}"
        df.to_parquet(buf_path, engine="pyarrow", index=False)

        client = storage.Client()
        bucket = client.bucket(DATA_LAKE_BUCKET)
        bucket.blob(blob_path).upload_from_filename(buf_path)

        logger.info(
            "archiver: wrote %d rows to gs://%s/%s", len(rows), DATA_LAKE_BUCKET, blob_path
        )
        return len(rows)
    except Exception as exc:
        logger.error("archiver: archive_expired_docs failed: %s", exc)
        raise ArchiveError(str(exc)) from exc
    finally:
        if buf_path and os.path.exists(buf_path):
            os.remove(buf_path)
