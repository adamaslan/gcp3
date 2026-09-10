#!/usr/bin/env bash
# Local stand-in for Cloud Scheduler — runs the gcp3 refresh cycle from a laptop
# against REAL Firestore, with Cloud Run entirely out of the path.
#
# Why this exists: Firestore is free-tier and kept working through the
# 2026-09-08 billing lapse; Cloud Run and Cloud Scheduler did not. Every
# scheduled pipeline pointed at one GCP project, so they all died together.
# This is the one path that does not share that dependency.
# See docs/wiki-gcp3/concept-local-first-resilience.md.
#
#   ./run_local_backup.sh                 # the daily set (fetch → bake → returns)
#   ./run_local_backup.sh fetch bake      # only these jobs
#   ./run_local_backup.sh --list          # show job → endpoint mapping
#   ./run_local_backup.sh --dry-run       # boot + /health only, no writes
#
# Secrets are read from Secret Manager at startup into the process environment.
# They are never written to disk, echoed, or passed on a command line.
#
# Written for bash 3.2 (macOS system bash) — no associative arrays.
set -euo pipefail

cd "$(dirname "$0")"

PROJECT="${GCP_PROJECT_ID:-ttb-lang1}"
PORT="${PORT:-8099}"
BASE="http://127.0.0.1:${PORT}"

# job | METHOD | PATH | in-default-run
# Mirrors `gcloud scheduler jobs list` on $PROJECT, verified 2026-09-10 against
# the live job definitions — which target /refresh/fetch and /refresh/bake.
# (REFRESH_CYCLE_ARCHITECTURE.md still documents /refresh/premarket and
# /refresh/all; those endpoints exist but no scheduler job calls them.)
JOB_TABLE='
fetch|POST|/refresh/fetch|yes
bake|POST|/refresh/bake|yes
returns|POST|/admin/compute-returns|yes
midday-yf|POST|/refresh/midday-yf|no
intraday|POST|/refresh/intraday?skip_gemini=true|no
purge|POST|/admin/purge-cache|no
seed|POST|/admin/seed-etf-history|no
audit|POST|/admin/audit-etf-history|no
'

job_rows() { printf '%s\n' "$JOB_TABLE" | grep -v '^$'; }
job_field() { job_rows | awk -F'|' -v j="$1" -v n="$2" '$1==j{print $n}'; }

if [ "${1:-}" = "--list" ]; then
  printf '%-12s %-42s %s\n' JOB ENDPOINT DEFAULT
  job_rows | awk -F'|' '{printf "%-12s %-42s %s\n", $1, $2" "$3, ($4=="yes"?"yes":"")}'
  exit 0
fi

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=1; shift; fi

if [ $# -gt 0 ]; then
  SELECTED="$*"
  for j in $SELECTED; do
    [ -n "$(job_field "$j" 2)" ] || { echo "unknown job: $j (see --list)" >&2; exit 2; }
  done
else
  SELECTED="$(job_rows | awk -F'|' '$4=="yes"{printf "%s ", $1}')"
fi

echo "[backup] project=$PROJECT  cache=firestore (REAL)  port=$PORT"
echo "[backup] jobs: $SELECTED"

# --- secrets: Secret Manager → process env, never printed -------------------
# Same names the Cloud Run revision binds. A missing optional key degrades
# gracefully (see concept-multi-source-fallback); FINNHUB_API_KEY is required.
# load_secret VAR NAME [ALT_NAME...] - first name that yields a value wins.
# Alternates exist because some secrets were re-created under a different case
# and the original name survives as an empty shell with zero enabled versions
# (e.g. OPENROUTER_API_KEY has none; openrouter-api-key holds the value).
load_secret() {
  var="$1"; shift
  for name in "$@"; do
    if val=$(gcloud secrets versions access latest --secret="$name" --project="$PROJECT" 2>/dev/null); then
      if [ -n "$val" ]; then
        export "$var=$val"
        unset val
        echo "[backup]   $var ok (from $name)"
        return 0
      fi
    fi
  done
  echo "[backup]   $var unavailable (skipped)"
  return 0
}
echo "[backup] loading secrets from Secret Manager..."
load_secret FINNHUB_API_KEY    FINNHUB_API_KEY
load_secret GEMINI_API_KEY     GEMINI_API_KEY
load_secret ALPHA_VANTAGE_KEY  ALPHA_VANTAGE_KEY
load_secret MASSIVE_API_KEY    MASSIVE_API_KEY
load_secret MISTRAL_KEY        MISTRAL_KEY
load_secret OPENROUTER_API_KEY openrouter-api-key OPENROUTER_API_KEY

[ -n "${FINNHUB_API_KEY:-}" ] || { echo "[backup] FATAL: FINNHUB_API_KEY unavailable - no market data source" >&2; exit 1; }

# A run-scoped token for the _verify_scheduler shared-secret fallback. Never the
# production SCHEDULER_SECRET: this server is bound to loopback and dies with
# the script, so a fresh random value is both sufficient and safer.
SCHEDULER_SECRET="$(openssl rand -hex 32)"
export SCHEDULER_SECRET

export GCP_PROJECT_ID="$PROJECT"
export CACHE_BACKEND=firestore   # REAL Firestore - the sqlite shim holds no prod data
export PORT
export RELOAD=""

# --- boot the production app locally ---------------------------------------
LOG="$(mktemp -t gcp3-local-backup)"
echo "[backup] starting app (log: $LOG)"
python main.py >"$LOG" 2>&1 &
APP_PID=$!
cleanup() {
  if kill -0 "$APP_PID" 2>/dev/null; then
    echo "[backup] stopping app (pid $APP_PID)"
    kill "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

i=0
while [ $i -lt 60 ]; do
  if curl -fsS --max-time 3 "$BASE/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "[backup] FATAL: app exited during startup - last 30 log lines:" >&2
    tail -30 "$LOG" >&2; exit 1
  fi
  sleep 1; i=$((i+1))
done
curl -fsS --max-time 5 "$BASE/health" || { echo "[backup] FATAL: /health never came up" >&2; tail -30 "$LOG" >&2; exit 1; }
echo
echo "[backup] app healthy"

if [ $DRY_RUN -eq 1 ]; then
  echo "[backup] --dry-run: booted and healthy against real Firestore, no jobs run"
  exit 0
fi

# --- run the jobs, in table (dependency) order -----------------------------
FAILED=0
RESP=/tmp/gcp3-backup-resp.json
for j in $(job_rows | awk -F'|' '{print $1}'); do
  case " $SELECTED " in *" $j "*) ;; *) continue ;; esac
  method="$(job_field "$j" 2)"
  path="$(job_field "$j" 3)"
  printf '[backup] %-12s %s %s ... ' "$j" "$method" "$path"
  start=$(date +%s)
  code=$(curl -s -o "$RESP" -w '%{http_code}' \
    -X "$method" -H "X-Scheduler-Token: $SCHEDULER_SECRET" \
    --max-time 900 "$BASE$path" || echo 000)
  echo "HTTP $code ($(( $(date +%s) - start ))s)"
  echo "[backup]   -> $(head -c 240 "$RESP")"
  [ "$code" = "200" ] || FAILED=1
done

echo
if [ $FAILED -eq 0 ]; then
  echo "[backup] all selected jobs returned 200 - Firestore is current without Cloud Run"
else
  echo "[backup] one or more jobs failed - see output above and $LOG" >&2
fi
exit $FAILED
