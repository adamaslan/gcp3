# Optimization Stack — Quick Reference

## Critical URLs

| Service | URL |
|---------|-----|
| **Backend** | `https://gcp3-backend-1007181159506.us-central1.run.app` |
| **Health Check** | `GET /health` → `{"status": "ok", "tools": 12}` |
| **Frontend (Vercel)** | `https://gcp3-frontend-739pct8ra-adam-aslans-projects.vercel.app` |

## GCP Resources

```bash
# View Cloud Run service
gcloud run services describe gcp3-backend --region us-central1

# View Cloud Scheduler jobs
gcloud scheduler jobs list --location=us-central1

# View Firestore TTL status
gcloud firestore fields describe expires_at --collection-group=gcp3_cache

# View Cloud Run logs (last 50 lines)
gcloud run services logs read gcp3-backend --region us-central1 --limit 50
```

## Key Endpoints

### Refresh (Cloud Scheduler only)
```bash
POST /refresh/premarket      # 8:30 AM ET (pre-market data)
POST /refresh/all            # 9:35 AM ET (full 8-stage warmup)
POST /refresh/intraday       # 12:00 PM & 4:15 PM ET (short-TTL refresh)
```

### Admin (Cloud Scheduler only)
```bash
POST /admin/compute-returns   # Precompute industry returns
POST /admin/purge-cache       # Clean expired docs (nightly 2 AM ET)
```

**Authorization:** Requires `X-Scheduler-Token` header = `SCHEDULER_SECRET` env var

## Cache Layers (Request → Response)

1. **Vercel Edge CDN** (~100ms globally) — ISR pages, `s-maxage` per route
2. **In-Memory Cache** (~0ms) — 60s TTL on Cloud Run (hot paths like industry_quotes)
3. **Firestore gcp3_cache** (~100ms) — 1–24h TTL, TTL-enabled auto-delete
4. **Firestore industry_cache** (~100ms) — precomputed returns, no API calls
5. **API Source** (1–12s) — Finnhub, yfinance, Gemini (fallback only)

## ISR Pages (Force-Dynamic + Revalidate)

All pages use `export const dynamic = "force-dynamic"` + `export const revalidate = N` pattern:

```typescript
export const dynamic = "force-dynamic";     // Skip prerendering
export const revalidate = 300;              // ISR revalidates after 5 min on first user request
```

| Revalidate | Pages |
|-----------|-------|
| 1 min | industry-tracker |
| 5 min | morning-brief |
| 30 min | screener, news-sentiment |
| 1 h | sector-rotation, macro-pulse, technical-signals, market-summary, industry-returns |
| 6 h | earnings-radar |
| 4 h | ai-summary, daily-blog, blog-review, correlation-article |

## API Routes (Cache-Control)

All routes return:
```
Cache-Control: public, s-maxage=N, stale-while-revalidate=M
```

Example:
```
s-maxage=300         # Vercel edge caches for 5 min
stale-while-revalidate=1800  # Falls back to stale data up to 30 min while revalidating
```

## Firestore Collections

| Collection | TTL | Purpose |
|-----------|-----|---------|
| `gcp3_cache` | Auto-delete via `expires_at` | Short-lived API cache (1–24h) |
| `industry_cache` | None | Precomputed industry returns (24h cache, written by scheduled job) |
| `etf_history` | None | Permanent ETF price history (read by compute_returns) |
| `analysis` / `summaries` | None | MCP pipeline output (read-only for backend) |

## Performance Checklist

### Every Day
- [ ] Scheduler jobs execute (check Cloud Logging)
- [ ] First user request after deploy completes (shouldn't timeout)

### Every Week
- [ ] Firestore collection sizes stable (gcp3_cache should not grow unbounded)
- [ ] Edge cache hit rate >90% (check Vercel dashboard)
- [ ] Backend p95 latency <500ms (should be mostly Firestore reads)

### Every Month
- [ ] Cost check: min-instances ($5–10) offset by reduced Firestore reads
- [ ] Adjust ISR revalidate times if business requirements change
- [ ] Review longest-running endpoints (might need optimization)

## Troubleshooting

### Backend Returns 503
**Likely cause:** Finnhub unavailable or cache miss with no fallback data.  
**Expected behavior:** Return 503 (never fake data).  
**Fix:** Check Finnhub status; wait for next scheduler warmup.

### Vercel Build Fails
**Likely cause:** `BACKEND_URL` not set in Vercel environment variables.  
**Fix:** Set in Vercel dashboard → Settings → Environment Variables.  
**Note:** All pages use `force-dynamic`, so build succeeds even without backend.

### Firestore Collection Growing Unbounded
**Likely cause:** TTL wasn't enabled, or old docs created before TTL.  
**Fix:**
```bash
# Verify TTL is active
gcloud firestore fields describe expires_at --collection-group=gcp3_cache

# Manual purge (one-time)
POST /admin/purge-cache (with X-Scheduler-Token header)
```

### High Firestore Reads
**Likely cause:** In-memory cache not hitting (instance restarted).  
**Expected:** First request after deploy hits Firestore; subsequent requests in 60s window hit memory.  
**Fix:** Monitor Cloud Run instance lifecycle; min-instances=1 keeps instances warm.

## Environment Variables (Backend)

```bash
# Required
GCP_PROJECT_ID          # "ttb-lang1"
FINNHUB_API_KEY         # Set in Cloud Run secrets
SCHEDULER_SECRET        # Set in Cloud Run secrets
BACKEND2_URL            # Optional, for fan-out calls

# Optional
GEMINI_MODEL           # "gemini-2.0-flash" (default)
ALPHA_VANTAGE_API_KEY  # For enrichment during warmup
```

## Environment Variables (Frontend)

```bash
# Required for build time
BACKEND_URL  # Set in Vercel Build Environment Variables
            # Example: https://gcp3-backend-1007181159506.us-central1.run.app
```

## Cost Breakdown (Estimated Monthly)

| Service | Cost | Notes |
|---------|------|-------|
| Cloud Run (gcp3-backend) | $5–10 | min-instances=1 (~730 instance-hours) |
| Firestore reads | $0.06–0.12 | ~200–300 reads/day instead of ~500–1000 |
| Firestore writes | $0.06–0.12 | Scheduler warmups |
| Firestore storage | $0.18–0.25 | Reduced with TTL cleanup |
| Vercel (Frontend) | ~$20 | Pro plan, includes unlimited bandwidth |
| **Total** | **~$25–40** | Savings: SWR cache hits, in-memory reduces Firestore |

---

## Links

- [Optimization Deep Dive](firestore_caching_warmup_optimization.md)
- [Deployment Status](OPTIMIZATION_DEPLOYMENT_STATUS.md)
- [Complete Report](OPTIMIZATION_COMPLETE_DEPLOYMENT_REPORT.md)
- [GCP Project](https://console.cloud.google.com/run?project=ttb-lang1)
- [Vercel Dashboard](https://vercel.com/adam-aslans-projects)
