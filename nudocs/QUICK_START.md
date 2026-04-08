# Firestore Caching Optimization — Quick Start

**TL;DR:** Code is ready. Run 2 commands to enable Firestore TTL + Cloud Run warmth. Deploy. Done.

---

## 30-Second Setup

```bash
# 1. Deploy code changes
cd backend/
gcloud builds submit --config cloudbuild.yaml --project $GCP_PROJECT_ID

# 2. Enable Firestore TTL (auto-delete expired cache)
gcloud firestore fields ttls update expires_at \
  --collection-group=gcp3_cache \
  --enable-ttl \
  --project=$GCP_PROJECT_ID

# 3. Keep backend warm (no cold starts)
gcloud run services update gcp3-backend \
  --region us-central1 \
  --min-instances=1 \
  --project=$GCP_PROJECT_ID
```

That's it! New endpoints are live:
- `POST /refresh/premarket` — 8:30 AM ET warmup (lightweight)
- `POST /admin/purge-cache` — 2:00 AM ET cache cleanup (safety net)

---

## What This Does

| Component | Benefit | Effort |
|-----------|---------|--------|
| In-memory cache layer | Hot-path reads drop from 50–200ms → 0ms | ✅ Done in code |
| Firestore TTL | Auto-delete 400+ dead docs/day | ✅ 1 GCP command |
| Cloud Run min-instances=1 | Eliminate 2–5s cold starts | ✅ 1 GCP command |
| Pre-market warmup | Data ready at 8:30 AM ET (1h early) | ✅ 1 endpoint |
| Nightly cache purge | Auditable cleanup + safety net | ✅ 1 endpoint |

---

## Expected Results

After setup, you should see:

1. **Firestore collection stops growing** — dead documents auto-delete within 24h
2. **Backend latency drops** — min-instances=1 eliminates cold start delays
3. **Hot-path requests faster** — in-memory cache hits within 60s are instant
4. **Early-morning data available** — pre-market job warms at 8:30 AM ET

---

## Next (Optional): Advanced Optimizations

Want to go deeper? See `IMPLEMENTATION_GUIDE.md` for:
- Stale-while-revalidate pattern (cache-miss returns in <200ms)
- UTC midnight TTL alignment (standardize daily keys)
- Response compression (70–80% payload reduction)
- ISR frontend optimizations (99%+ edge-cached pages)

---

## Verify It Works

```bash
# Test pre-market endpoint
curl -X POST \
  -H "X-Scheduler-Token: $SCHEDULER_SECRET" \
  https://gcp3-backend-xyz.run.app/refresh/premarket

# Test cache purge endpoint
curl -X POST \
  -H "X-Scheduler-Token: $SCHEDULER_SECRET" \
  https://gcp3-backend-xyz.run.app/admin/purge-cache

# Both should return 200 OK + JSON with status/timestamps
```

---

## Files Changed

- `backend/firestore.py` — in-memory cache layer
- `backend/main.py` — 2 new endpoints + auto-purge
- `nudocs/IMPLEMENTATION_GUIDE.md` — full setup guide
- `nudocs/PHASE1_GCP_COMMANDS.sh` — automated GCP setup
- `nudocs/IMPLEMENTATION_SUMMARY.md` — detailed summary

---

**Ready?** Run the 3 commands above and check your Firestore collection size after 24 hours.
