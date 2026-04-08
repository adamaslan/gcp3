# Firestore Caching Optimization — Implementation Guide

**Date:** 2026-04-07  
**Status:** Phase 1–3 implemented in code. Requires manual GCP configuration.

---

## What Has Been Implemented

### ✅ Phase 2: In-Memory Cache Layer (firestore.py)

Added a Python-level dict cache with time-based expiry:

```python
_MEM_CACHE: dict[str, tuple[float, dict]] = {}

def mem_get(key: str, max_age: float = 60.0) -> dict | None:
    """Get from in-memory cache if not stale."""

def mem_set(key: str, value: dict) -> None:
    """Set in-memory cache with current timestamp."""
```

**Effect:** Repeated cache reads within 60 seconds hit in-memory (~0ms) instead of Firestore (50-200ms).

**Integration:**
- `get_cache()` now checks in-memory first, then Firestore, then returns None
- `set_cache()` populates both Firestore and in-memory on write
- Eliminates Firestore reads for hot paths: `industry_quotes`, `screener`, `news_sentiment`

**Tier 1 Performance:**
```
Request 1 → Firestore read (100ms) → mem_set → in-memory cache
Request 2 (within 60s) → mem_get (0ms) ✅
Request 3 (after 60s) → Firestore read (100ms) again
```

---

### ✅ Phase 3A: Pre-Market Warmup (main.py)

Added `/refresh/premarket` endpoint for 8:30 AM ET:

```python
POST /refresh/premarket
```

**Warms only lightweight endpoints:**
- `get_morning_brief()` — news summary
- `get_news_sentiment()` — social sentiment
- `get_macro_pulse()` — macro indicators

**Skips:**
- Industry tracker (50 Finnhub calls)
- Earnings radar (EPS data)
- AI synthesis (heavy computation)

**Benefit:** Early-morning users (before 9:35 AM market open) get warm data without waiting for the full refresh.

---

### ✅ Phase 3B: Admin Cache Purge (main.py)

Added `/admin/purge-cache` endpoint:

```python
POST /admin/purge-cache
X-Scheduler-Token: <token>
```

**Function:**
- Queries all documents in `gcp3_cache` with `expires_at < now`
- Deletes in batches of 450 (Firestore limit is 500/batch)
- Returns count of deleted documents and timestamp

**This is a safety net:** Works alongside native Firestore TTL (Phase 1A). The TTL handles automatic cleanup; this endpoint provides:
- Visibility into expired document count
- Manual cleanup option during development/testing
- Auditable log of purge operations

---

## What Still Requires Manual GCP Setup (Phase 1)

### Phase 1A: Enable Native Firestore TTL

Run this GCP CLI command to enable automatic deletion of expired cache documents:

```bash
gcloud firestore fields ttls update expires_at \
  --collection-group=gcp3_cache \
  --enable-ttl \
  --project=$GCP_PROJECT_ID
```

**Effect:**
- Firestore automatically deletes documents where `expires_at` timestamp has passed
- Cleanup happens within ~24 hours of expiry
- Zero read cost — deletions don't consume reads
- Eliminates the 400+ dead documents/day problem

**Verify:**
```bash
gcloud firestore fields describe expires_at --project=$GCP_PROJECT_ID
# Should show: ttlConfig: {state: "ACTIVE"}
```

### Phase 1B: Set Cloud Run Min Instances

Run this command to ensure the backend is never cold:

```bash
gcloud run services update gcp3-backend \
  --region us-central1 \
  --min-instances=1 \
  --project=$GCP_PROJECT_ID
```

**Effect:**
- Cloud Run keeps 1 instance warm 24/7
- Eliminates 2-5s cold start latency on first request
- Cost: ~$5-10/month on free-tier pricing

**Verify:**
```bash
gcloud run services describe gcp3-backend \
  --region us-central1 \
  --project=$GCP_PROJECT_ID | grep minInstances
# Should show: minInstances: 1
```

---

## Deployment Steps

### Step 1: Deploy Code Changes

```bash
cd backend/
gcloud builds submit --config cloudbuild.yaml --project $GCP_PROJECT_ID
```

This deploys:
- Updated `firestore.py` (in-memory cache layer)
- Updated `main.py` (`/refresh/premarket`, `/admin/purge-cache` endpoints)

**Verification after deploy:**
```bash
# Test the new endpoints
curl -H "X-Scheduler-Token: $SCHEDULER_SECRET" \
  https://gcp3-backend-xyz.run.app/refresh/premarket

curl -H "X-Scheduler-Token: $SCHEDULER_SECRET" \
  https://gcp3-backend-xyz.run.app/admin/purge-cache
```

### Step 2: Enable Firestore Native TTL (One-Time)

```bash
gcloud firestore fields ttls update expires_at \
  --collection-group=gcp3_cache \
  --enable-ttl \
  --project=$GCP_PROJECT_ID
```

### Step 3: Set Cloud Run Min Instances (One-Time)

```bash
gcloud run services update gcp3-backend \
  --region us-central1 \
  --min-instances=1 \
  --project=$GCP_PROJECT_ID
```

### Step 4: Add Cloud Scheduler Jobs (One-Time)

Create or update these 3 scheduler jobs (in addition to the existing ones):

#### Pre-Market Warmup (NEW)

```bash
gcloud scheduler jobs create http gcp3-premarket-warmup \
  --schedule="30 12 * * 1-5" \
  --http-method=POST \
  --uri=https://gcp3-backend-xyz.run.app/refresh/premarket \
  --headers="X-Scheduler-Token=$SCHEDULER_SECRET" \
  --time-zone="UTC" \
  --location=us-central1 \
  --project=$GCP_PROJECT_ID
# OR update if exists:
# gcloud scheduler jobs update http gcp3-premarket-warmup ...
```

**Cron breakdown:**
- `30 12` = 12:30 UTC = 8:30 AM ET (1 hour before market open)
- `* * 1-5` = Monday–Friday only

#### Nightly Cache Purge (NEW)

```bash
gcloud scheduler jobs create http gcp3-nightly-cache-purge \
  --schedule="0 6 * * *" \
  --http-method=POST \
  --uri=https://gcp3-backend-xyz.run.app/admin/purge-cache \
  --headers="X-Scheduler-Token=$SCHEDULER_SECRET" \
  --time-zone="UTC" \
  --location=us-central1 \
  --project=$GCP_PROJECT_ID
```

**Cron breakdown:**
- `0 6 * * *` = 6:00 AM UTC = 2:00 AM ET (nightly safety net)

#### Update Existing Jobs

If you already have `gcp3-morning-full-refresh` and `gcp3-eod-intraday-refresh`, no changes needed. But verify they exist:

```bash
gcloud scheduler jobs list --location=us-central1 --project=$GCP_PROJECT_ID
```

---

## Expected Outcomes After Full Implementation

| Metric | Before | After |
|--------|--------|-------|
| Cold start latency | 2–5s | 0s (min-instances=1) |
| Cache-miss response time | 2–12s | <500ms (in-memory for 60s) |
| Firestore dead documents/day | 400+ | 0 (native TTL auto-deletes) |
| Firestore reads/day | 500–1000 | 200–300 (in-memory hits) |
| Industry quotes latency (hot path) | 50–200ms | 0–50ms (in-memory) |
| Pre-market data availability | 9:35 AM ET | 8:30 AM ET |

---

## Optional Enhancements (Phase 2–4)

### Stale-While-Revalidate (Recommended for Phase 2)

Currently, if Firestore cache expires, the endpoint blocks on a full API call (2–8s latency). Wire `get_cache_stale()` into all endpoints to return last-known data instantly while triggering a background refresh:

```python
async def get_screener_data():
    fresh = get_cache("screener:" + today)
    if fresh:
        return fresh

    stale, stale_as_of = get_cache_stale("screener:" + today)
    if stale:
        asyncio.create_task(_refresh_screener())  # background refresh
        return {**stale, "_stale_as_of": stale_as_of}

    # No data at all — must block on fresh fetch
    return await _refresh_screener()
```

**Benefit:** Cache misses return in <200ms instead of 2–8s.

### UTC Midnight TTL Alignment (Phase 3)

Standardize all daily cache keys to use UTC midnight expiry:

```python
from datetime import datetime, timezone, timedelta

def ttl_until_midnight_utc() -> datetime:
    """Return datetime for tomorrow at midnight UTC."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).date()
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc)

set_cache("morning_brief:" + today, data, ttl_hours=None)  # uses midnight TTL instead
```

**Modules needing update:**
- `morning.py` (8h TTL → midnight)
- `screener.py` (1h TTL → keep short, use UTC date)
- `macro_pulse.py` (2h TTL → keep short)
- And 8 others (see optimization guide for full list)

### Response Compression (One-Line Fix)

Already added `GZipMiddleware` in `main.py`, but ensure it's active:

```python
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

**Effect:** Industry tracker payloads shrink from 35–50 KB to 8–12 KB.

---

## Troubleshooting

### Memory Cache Not Hitting?

Check if data is in-memory by looking at response time:
```bash
curl -w "@curl-format.txt" https://gcp3-backend-xyz.run.app/industry-quotes
# If time_starttransfer is <50ms: memory cache hit ✅
# If >100ms: Firestore hit (stale or fresh)
```

### Firestore TTL Not Deleting?

TTL deletion is not instantaneous — can take 24 hours. Monitor:
```bash
# Count documents in gcp3_cache
gcloud firestore --project=$GCP_PROJECT_ID <<EOF
select COUNT(*) from gcp3_cache;
EOF
```

Alternatively, manually trigger purge-cache nightly:
```bash
curl -X POST -H "X-Scheduler-Token: $SCHEDULER_SECRET" \
  https://gcp3-backend-xyz.run.app/admin/purge-cache
```

### Pre-Market Job Not Running?

Verify Cloud Scheduler job exists and has correct auth:
```bash
gcloud scheduler jobs describe gcp3-premarket-warmup \
  --location=us-central1 \
  --project=$GCP_PROJECT_ID
```

Check recent execution logs:
```bash
gcloud scheduler jobs list-runs gcp3-premarket-warmup \
  --location=us-central1 \
  --project=$GCP_PROJECT_ID
```

---

## Next Steps

1. **Immediate:** Deploy code (`gcloud builds submit`), run Phase 1 GCP commands
2. **Week 2:** Monitor metrics (see dashboard), verify TTL is deleting expired docs
3. **Week 3+:** Implement stale-while-revalidate, align daily cache keys to UTC midnight
4. **Month 2:** Frontend ISR optimizations (Phase 5) — now that backend is warm, remove `force-dynamic` from 13 pages

---

**Questions?** See the full optimization guide in `nudocs/firestore_caching_warmup_optimization.md`.
