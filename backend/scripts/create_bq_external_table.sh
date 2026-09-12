#!/usr/bin/env bash
# Tip 3 (docs/data-monetization-25-tips.md): create the BigQuery external
# table over the GCS Parquet lake written by archiver.py.
#
# Run this ONCE, after /admin/purge-cache has run at least once in prod and
# written a real Parquet file under gs://nwf-data-lake/gcp3_cache/dt=.../ —
# BigQuery's hive-partitioned external tables require at least one file to
# exist at creation time (autodetect and explicit schema both fail on an
# empty prefix).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-ttb-lang1}"
DATASET="nwf"
TABLE="gcp3_cache_archive"
# Same env var + default as backend/archiver.py's DATA_LAKE_BUCKET — a
# deployment that overrides it must have this external table point at the
# same bucket the archiver actually writes to, not a hardcoded name.
DATA_LAKE_BUCKET="${NWF_DATA_LAKE_BUCKET:-nwf-data-lake}"
BUCKET_PREFIX="gs://${DATA_LAKE_BUCKET}/gcp3_cache/"

def_file="$(mktemp)"
cat > "$def_file" <<EOF
{
  "sourceFormat": "PARQUET",
  "sourceUris": ["${BUCKET_PREFIX}*"],
  "hivePartitioningOptions": {
    "mode": "AUTO",
    "sourceUriPrefix": "${BUCKET_PREFIX}"
  }
}
EOF

bq mk --table --project_id="${PROJECT_ID}" \
  --external_table_definition="${def_file}" \
  "${DATASET}.${TABLE}"

rm -f "${def_file}"
echo "Created ${PROJECT_ID}:${DATASET}.${TABLE} over ${BUCKET_PREFIX}*"
