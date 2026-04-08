# Deployment Checklist — Complete Implementation

**Quick reference for deploying Phases 1–5 of the Firestore Caching & ISR Optimization**

---

## Phase 1: GCP Configuration (Manual)

**⏱️ Time: 5 minutes**

- [ ] Verify `GCP_PROJECT_ID` is set: `echo $GCP_PROJECT_ID`
- [ ] Enable Firestore TTL:
  ```bash
  gcloud firestore fields ttls update expires_at \
    --collection-group=gcp3_cache \
    --enable-ttl \
    --project=$GCP_PROJECT_ID
  ```
- [ ] Verify TTL enabled:
  ```bash
  gcloud firestore fields describe expires_at \
    --project=$GCP_PROJECT_ID | grep -A2 ttlConfig
  # Should show: state: "ACTIVE"
  ```
- [ ] Set Cloud Run min-instances:
  ```bash
  gcloud run services update gcp3-backend \
    --region us-central1 \
    --min-instances=1 \
    --project=$GCP_PROJECT_ID
  ```
- [ ] Verify min-instances set:
  ```bash
  gcloud run services describe gcp3-backend \
    --region us-central1 \
    --project=$GCP_PROJECT_ID | grep minInstances
  # Should show: minInstances: 1
  ```

---

## Phase 2–3: Backend Deployment

**⏱️ Time: 10–15 minutes (includes build + deploy)**

- [ ] Verify backend code changes:
  - [ ] `backend/firestore.py` — in-memory cache layer present
  - [ ] `backend/main.py` — `/refresh/premarket` endpoint present
  - [ ] `backend/main.py` — `/admin/purge-cache` endpoint present
- [ ] Deploy backend:
  ```bash
  cd backend/
  gcloud builds submit --config cloudbuild.yaml --project $GCP_PROJECT_ID
  ```
- [ ] Wait for deployment to complete (check Cloud Run console)
- [ ] Test pre-market endpoint:
  ```bash
  curl -X POST \
    -H "X-Scheduler-Token: $SCHEDULER_SECRET" \
    https://gcp3-backend-xyz.run.app/refresh/premarket
  # Should return: {"status": "premarket_warmed", ...}
  ```
- [ ] Test purge endpoint:
  ```bash
  curl -X POST \
    -H "X-Scheduler-Token: $SCHEDULER_SECRET" \
    https://gcp3-backend-xyz.run.app/admin/purge-cache
  # Should return: {"deleted": N, "timestamp": "2026-04-07T..."}
  ```

---

## Phase 3: Cloud Scheduler Jobs

**⏱️ Time: 5 minutes (or use automated script)**

- [ ] Get backend URL:
  ```bash
  BACKEND_URL=$(gcloud run services describe gcp3-backend \
    --region us-central1 \
    --project=$GCP_PROJECT_ID \
    --format='value(status.url)')
  echo $BACKEND_URL
  ```

- [ ] Create pre-market warmup job:
  ```bash
  gcloud scheduler jobs create http gcp3-premarket-warmup \
    --schedule="30 12 * * 1-5" \
    --http-method=POST \
    --uri="$BACKEND_URL/refresh/premarket" \
    --headers="X-Scheduler-Token=$SCHEDULER_SECRET" \
    --time-zone="UTC" \
    --location=us-central1 \
    --project=$GCP_PROJECT_ID
  ```

- [ ] Create nightly purge job:
  ```bash
  gcloud scheduler jobs create http gcp3-nightly-cache-purge \
    --schedule="0 6 * * *" \
    --http-method=POST \
    --uri="$BACKEND_URL/admin/purge-cache" \
    --headers="X-Scheduler-Token=$SCHEDULER_SECRET" \
    --time-zone="UTC" \
    --location=us-central1 \
    --project=$GCP_PROJECT_ID
  ```

- [ ] Verify jobs created:
  ```bash
  gcloud scheduler jobs list --location=us-central1 \
    --project=$GCP_PROJECT_ID
  # Should show 5 jobs: premarket, morning-full-refresh, midday-intraday, eod-intraday, nightly-cache-purge
  ```

---

## Phase 5: Frontend Deployment

**⏱️ Time: 5–10 minutes (includes build + deploy)**

- [ ] Verify frontend code changes:
  - [ ] 14 pages updated with `revalidate` values (not `force-dynamic`)
  - [ ] Portfolio Analyzer keeps `force-dynamic` + has comment
  - [ ] 16 API routes have `Cache-Control` headers
  - [ ] `vercel.json` has blanket `no-store` removed
- [ ] Build frontend:
  ```bash
  cd frontend/
  npm run build
  # Should complete in <2 minutes with warm backend caches
  ```
- [ ] Deploy to Vercel:
  ```bash
  vercel deploy --prod
  ```
- [ ] Verify deployment succeeded (check Vercel dashboard)

---

## Post-Deployment Verification

**⏱️ Time: 15–20 minutes (initial checks)**

### Backend Health

- [ ] Backend is running:
  ```bash
  curl https://gcp3-backend-xyz.run.app/health
  # Should return: {"status": "ok", "version": "2.1.0", ...}
  ```

- [ ] In-memory cache is working (check logs):
  ```bash
  gcloud run services logs read gcp3-backend \
    --region us-central1 \
    --limit 50 \
    --project=$GCP_PROJECT_ID | grep -i "cache"
  ```

### Frontend Headers

- [ ] Check Cache-Control headers on API routes:
  ```bash
  curl -I https://your-deployed-site.vercel.app/api/morning-brief
  # Should show: Cache-Control: public, s-maxage=300, stale-while-revalidate=1800

  curl -I https://your-deployed-site.vercel.app/api/industry-quotes
  # Should show: Cache-Control: public, s-maxage=60, stale-while-revalidate=300
  ```

- [ ] Check pages have ISR enabled:
  ```bash
  # Visit a page and check Network tab in DevTools
  # Should show quick load times (~100ms for initial edge hit)
  # Subsequent loads should be instant (cached)
  ```

### Firestore Monitoring

- [ ] Check collection size (should stabilize within 24h):
  ```bash
  # Cloud Console → Firestore → gcp3_cache collection
  # Count should level off as TTL auto-deletes expired docs
  ```

- [ ] Verify TTL is deleting:
  ```bash
  # After 24h, collection should shrink significantly
  # Expired documents should be auto-deleted (within ~24h of expiry)
  ```

---

## 24-Hour Monitoring

**Track these metrics in Vercel & GCP dashboards:**

- [ ] **Edge cache hit ratio** — should reach 95%+ within 24h
- [ ] **Page load times (p50)** — should be ~100ms
- [ ] **Page load times (p95)** — should be <500ms
- [ ] **Backend requests** — should drop to ~1 per 100 users
- [ ] **Firestore reads** — should drop 60–70%
- [ ] **Firestore collection size** — should stabilize (no unbounded growth)
- [ ] **Cloud Run latency** — cold starts eliminated by min-instances=1
- [ ] **Cloud Scheduler jobs** — all 5 jobs running successfully

---

## Rollback Instructions (If Needed)

### Revert Backend
```bash
# Revert to previous Cloud Run revision
gcloud run services update-traffic gcp3-backend \
  --to-revisions [PREVIOUS_REVISION_ID]=100 \
  --region us-central1 \
  --project=$GCP_PROJECT_ID

# Or delete scheduler jobs
gcloud scheduler jobs delete gcp3-premarket-warmup \
  --location=us-central1 --project=$GCP_PROJECT_ID
gcloud scheduler jobs delete gcp3-nightly-cache-purge \
  --location=us-central1 --project=$GCP_PROJECT_ID
```

### Revert Frontend
```bash
vercel rollback
```

### Restore GCP Settings
```bash
# Disable Firestore TTL (if needed)
gcloud firestore fields ttls update expires_at \
  --collection-group=gcp3_cache \
  --disable-ttl \
  --project=$GCP_PROJECT_ID

# Remove min-instances (revert to 0)
gcloud run services update gcp3-backend \
  --region us-central1 \
  --min-instances=0 \
  --project=$GCP_PROJECT_ID
```

---

## Troubleshooting

### Backend Issues

**Endpoint returns 401 Unauthorized:**
- Check `SCHEDULER_SECRET` env var matches Cloud Run
- Verify `X-Scheduler-Token` header is set in curl command

**Pre-market endpoint times out:**
- Check backend logs: `gcloud run services logs read gcp3-backend`
- Verify Finnhub API key is valid
- Check network connectivity to Finnhub

**Purge endpoint doesn't delete anything:**
- No documents have expired yet (TTL deletion is ~24h)
- Check Firestore console for documents with past `expires_at` timestamps

### Frontend Issues

**ISR revalidation is slow:**
- Verify backend cache is warm: check gcp3_cache collection
- Check Firestore latency in backend logs
- Verify scheduler jobs are running on schedule

**Cache-Control headers not present:**
- Check `vercel.json` — should NOT have blanket `no-store`
- Redeploy frontend: `vercel deploy --prod`
- Clear Vercel cache if needed

**Portfolio analyzer broken after ISR migration:**
- Should still work (kept `force-dynamic`)
- Check browser console for errors
- Verify `BACKEND_URL` is set in Vercel env vars

---

## Quick Success Checklist

✅ After deployment, you should have:

- [ ] Firestore native TTL active (expires_at field)
- [ ] Cloud Run min-instances=1 (no cold starts)
- [ ] 5 Cloud Scheduler jobs running (3 refresh + 1 premarket + 1 purge)
- [ ] 14 pages using ISR (not force-dynamic)
- [ ] 16 API routes with Cache-Control headers
- [ ] vercel.json cleaned up (no blanket no-store)
- [ ] Edge cache hit ratio 95%+ within 24h
- [ ] Page loads ~100ms (edge cache hits)
- [ ] Backend requests ~1 per 100 users
- [ ] Firestore collection size stabilized

---

## Documentation References

- **Full deployment guide:** `COMPLETE_IMPLEMENTATION_SUMMARY.md`
- **Backend setup:** `IMPLEMENTATION_GUIDE.md`
- **Frontend ISR:** `ISR_IMPLEMENTATION_COMPLETE.md`
- **Quick start:** `QUICK_START.md`
- **GCP commands:** `PHASE1_GCP_COMMANDS.sh`

---

**Status:** Ready to execute. Start with Phase 1 GCP commands, then backend, then frontend.

Estimated total time: **25–35 minutes** for full deployment + initial verification.
