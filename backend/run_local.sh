#!/usr/bin/env bash
# Run the GCP3 Finance API locally — no GCP project, Firestore, or service
# account required. Cache is backed by a local SQLite file (local_firestore.py).
#
#   ./run_local.sh          # starts on http://localhost:8080 (docs at /docs)
#   PORT=8010 ./run_local.sh
#
# Market-data keys (FINNHUB_API_KEY, etc.) are read from backend/.env or the
# environment. Missing optional keys degrade gracefully; see .env.local.example.
set -euo pipefail

cd "$(dirname "$0")"

export CACHE_BACKEND="${CACHE_BACKEND:-sqlite}"
export LOCAL_CACHE_DB="${LOCAL_CACHE_DB:-./local_cache.db}"
export PORT="${PORT:-8080}"
export RELOAD="${RELOAD:-1}"

echo "[run_local] CACHE_BACKEND=$CACHE_BACKEND  DB=$LOCAL_CACHE_DB"
echo "[run_local] API  → http://localhost:$PORT"
echo "[run_local] Docs → http://localhost:$PORT/docs"

python main.py
