# ISR Frontend Optimization — Phase 5 Migration Guide

**Date:** 2026-04-07  
**Prerequisite:** Complete Phases 1–4 backend optimizations (in-memory cache, native TTL, warm scheduler)  
**Scope:** Remove `force-dynamic` from 12 pages, add `revalidate` hints, set API route `Cache-Control` headers

---

## Why ISR Works Now

The original `isr_optimization_strategy.md` recommended conservative `revalidate` values (6–24 hours) because it assumed backend cache misses would trigger expensive Finnhub/Gemini API calls.

**With Phases 1–4 in place:**
- Every cache miss hits warm Firestore (~100ms) instead of API (~2–8s)
- Scheduler keeps caches fresh 3x/day (8:30 AM, 12 PM, 4:15 PM)
- In-memory cache hits are instant (0ms) for 60s
- Stale-while-revalidate returns last-known data instantly + async refresh

**Result:** We can now use **much shorter ISR intervals** without increasing backend load. Shorter intervals = fresher data for users at near-zero cost.

---

## Strategy Overview

```
Before: force-dynamic on every page
├── Every user request → full SSR to Cloud Run
├── Cloud Run → Finnhub/Gemini API calls
└── Latency: 1–3s per page view, 100 requests/100 users

After: ISR on most pages + warm backend caches
├── 99% of users → serve cached HTML from Vercel edge CDN (~100ms)
├── 1% on revalidation window → background refresh to warm cache (~100ms)
└── Latency: ~100ms per page view, ~1 backend request/100 users
```

---

## Page-by-Page Migration

### Tier 1: High-Frequency Pages (Live/Intraday Data)

These pages show data that changes during market hours. Use short ISR intervals (1–30 minutes) combined with scheduler warmups.

#### Industry Tracker

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 60; // 1 minute
```

**Why 60s?**
- Quotes refresh every 60s via scheduler (9:35 AM, 12 PM, 4:15 PM)
- In-memory cache hits are 0ms for first 60s
- Users see live-ish data within 1 minute

**Backend Cache TTL:**
- Quotes: 60s (in-memory + Firestore)
- Returns: precomputed daily (Phase 4)

---

#### Morning Brief

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 300; // 5 minutes
```

**Why 300s?**
- Data computed once at 9:35 AM, cached for 8 hours
- Scheduler warms at 8:30 AM (premarket) + 9:35 AM (full)
- ISR revalidation hits warm Firestore cache (~100ms)
- Users see data at most 5 minutes stale

---

#### Screener

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 1800; // 30 minutes
```

**Why 1800s?**
- Screener signal data recalculates hourly (1h Firestore TTL)
- Scheduler refreshes 3x/day (9:35 AM, 12 PM, 4:15 PM)
- 30-min ISR means at most 2 revalidations per hour, all hit warm cache
- Users see data at most 30 minutes stale (acceptable for signals)

---

#### News Sentiment

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 1800; // 30 minutes
```

**Why 1800s?**
- Same as screener: 1h TTL, refreshed 3x/day
- News cycles hourly; 30-min staleness is acceptable
- All ISR revalidations hit warm Firestore cache

---

### Tier 2: Mid-Frequency Pages (Multi-Hour Data)

These pages show data that shifts slowly. Use longer ISR intervals (1 hour) because underlying data doesn't change frequently.

#### Sector Rotation

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 3600; // 1 hour
```

**Why 3600s?**
- Momentum scores shift slowly throughout the day
- Backend cache TTL: 2 hours
- Scheduler refreshes 3x/day
- 1h ISR means revalidation happens at most once between scheduler runs
- Each revalidation reads from warm Firestore (~100ms)

---

#### Macro Pulse

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 3600; // 1 hour
```

**Why 3600s?**
- Same pattern as sector rotation
- Cross-asset indicators move slowly
- 1h ISR + 2h backend TTL = good coverage

---

#### Technical Signals

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 3600; // 1 hour
```

**Why 3600s?**
- Reads from permanent `analysis` collection (MCP pipeline output)
- Zero API calls on revalidation — just Firestore reads
- Updated periodically, not on every request
- 1h ISR is more than sufficient

---

#### Market Summary

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 3600; // 1 hour
```

**Why 3600s?**
- Reads precomputed summaries from MCP pipeline
- Zero API cost on revalidation
- 1h ISR keeps data fresh all day

---

### Tier 3: Daily Data (Computed Once Per Day)

These pages are computed once at 9:35 AM and don't change until the next day. Massive ISR win — a single revalidation after morning warmup serves every user for 24 hours.

#### AI Summary

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 14400; // 4 hours
```

**Why 14400s?**
- Generated once daily by Gemini at 9:35 AM (Stage 5)
- Cached until midnight UTC
- 4h still overkill for same-day data, but catches rare mid-day regeneration
- All ISR revalidations within a day hit the same cache entry

---

#### Daily Blog

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 14400; // 4 hours
```

**Why 14400s?**
- Same as AI Summary — generated once daily at 9:35 AM
- Cached until midnight UTC
- 4h ISR ensures fresh content is deployed ~2 revalidations per day

---

#### Blog Review

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 14400; // 4 hours
```

**Why 14400s?**
- Review of daily blog (depends on Stage 6)
- Same daily cadence as Daily Blog
- 4h ISR pattern

---

#### Correlation Article

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 14400; // 4 hours
```

**Why 14400s?**
- Cross-asset correlation analysis (generated once daily)
- Cached until midnight UTC
- Same daily refresh pattern

---

#### Earnings Radar

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 21600; // 6 hours
```

**Why 21600s?**
- EPS calendar data genuinely doesn't change intraday
- 6h backend cache TTL (earnings don't refresh mid-day)
- 6h ISR aligns with backend TTL
- Much longer ISR than other daily pages because data is truly static during trading day

---

#### Industry Returns

**Current:**
```tsx
export const dynamic = "force-dynamic";
```

**Change to:**
```tsx
export const revalidate = 3600; // 1 hour
```

**Why 3600s?**
- After Phase 4: returns are precomputed off the request path
- ISR revalidation reads from `industry_cache` — 1 Firestore read, zero API calls
- Users see fresh returns hourly (more responsive than daily-only updates)
- Aligns with industry tracker quote refresh cadence

---

### Tier 4: User-Specific Pages (Cannot Use ISR)

#### Portfolio Analyzer

**Keep as-is:**
```tsx
export const dynamic = "force-dynamic";
```

**Why?**
- Accepts user-provided `?tickers=` query params
- Infinite input space — impossible to precompute all combinations
- Must remain dynamic for every request

**Optimization:** Use client-side SWR/React Query with the API proxy route instead. The backend's in-memory + Firestore cache still helps — repeated identical ticker combos within 60s hit memory cache.

---

## API Route Cache Headers

Update API proxy routes in `frontend/src/app/api/` to set `Cache-Control` headers aligned with data freshness. These headers tell the Vercel edge network how long to cache responses.

### Before

```tsx
// src/app/api/morning-brief/route.ts
export async function GET() {
  const base = process.env.BACKEND_URL;
  const res = await fetch(`${base}/morning-brief`);
  return res;
}
// No Cache-Control header — defaults to no-store (no edge caching)
```

### After

```tsx
// src/app/api/morning-brief/route.ts
export async function GET() {
  const base = process.env.BACKEND_URL;
  const res = await fetch(`${base}/morning-brief`);
  
  return new Response(res.body, {
    status: res.status,
    headers: {
      ...Object.fromEntries(res.headers),
      "Cache-Control": "s-maxage=300, swr=1800", // 5min max, 30min stale-while-revalidate
    },
  });
}
```

### Cache-Control Header Guide

**Format:** `s-maxage=X, swr=Y`
- `s-maxage=X` — Vercel edge caches for X seconds
- `swr=Y` — Edge can serve stale data for Y seconds while revalidating in background

### API Routes: Complete List

| Route | Recommended `Cache-Control` | Why |
|-------|------------------------------|-----|
| `/api/morning-brief` | `s-maxage=300, swr=1800` | 5min + 30min stale |
| `/api/screener` | `s-maxage=1800, swr=3600` | 30min + 1h stale |
| `/api/sector-rotation` | `s-maxage=3600, swr=7200` | 1h + 2h stale |
| `/api/macro-pulse` | `s-maxage=3600, swr=7200` | 1h + 2h stale |
| `/api/earnings-radar` | `s-maxage=21600, swr=43200` | 6h + 12h stale |
| `/api/news-sentiment` | `s-maxage=1800, swr=3600` | 30min + 1h stale |
| `/api/ai-summary` | `s-maxage=14400, swr=28800` | 4h + 8h stale |
| `/api/technical-signals` | `s-maxage=3600, swr=7200` | 1h + 2h stale |
| `/api/daily-blog` | `s-maxage=14400, swr=28800` | 4h + 8h stale |
| `/api/market-summary` | `s-maxage=3600, swr=7200` | 1h + 2h stale |
| `/api/industry-quotes` | `s-maxage=60, swr=300` | 1min + 5min stale |
| `/api/industry-tracker` | `s-maxage=60, swr=300` | 1min + 5min stale |
| `/api/industry-returns` | `s-maxage=300, swr=600` | 5min + 10min stale |

---

## Updating vercel.json

Remove blanket `no-store` if present:

**Before:**
```json
{
  "crons": [...],
  "rewrites": [...],
  "headers": [
    {
      "source": "/api/(.*)",
      "headers": [{ "key": "Cache-Control", "value": "no-store" }]
    }
  ]
}
```

**After:**
```json
{
  "crons": [...],
  "rewrites": [...]
  // Remove the blanket no-store header — per-route headers take precedence
}
```

This allows individual API routes to set their own `Cache-Control` headers.

---

## Implementation Checklist

### Phase 5A: Remove `force-dynamic` from Pages (Week 1)

- [ ] Morning Brief → `revalidate = 300`
- [ ] Industry Tracker → `revalidate = 60`
- [ ] Screener → `revalidate = 1800`
- [ ] Sector Rotation → `revalidate = 3600`
- [ ] Macro Pulse → `revalidate = 3600`
- [ ] Earnings Radar → `revalidate = 21600`
- [ ] News Sentiment → `revalidate = 1800`
- [ ] Technical Signals → `revalidate = 3600`
- [ ] Market Summary → `revalidate = 3600`
- [ ] AI Summary → `revalidate = 14400`
- [ ] Daily Blog → `revalidate = 14400`
- [ ] Blog Review → `revalidate = 14400`
- [ ] Correlation Article → `revalidate = 14400`
- [ ] Industry Returns → `revalidate = 3600`
- [ ] Portfolio Analyzer → **Keep `force-dynamic`**

### Phase 5B: Add Cache-Control Headers to API Routes (Week 1)

- [ ] `/api/morning-brief`
- [ ] `/api/screener`
- [ ] `/api/sector-rotation`
- [ ] `/api/macro-pulse`
- [ ] `/api/earnings-radar`
- [ ] `/api/news-sentiment`
- [ ] `/api/ai-summary`
- [ ] `/api/technical-signals`
- [ ] `/api/daily-blog`
- [ ] `/api/market-summary`
- [ ] `/api/industry-quotes` (update if exists)
- [ ] `/api/industry-tracker` (update if exists)
- [ ] `/api/industry-returns` (update if exists)

### Phase 5C: Update vercel.json (Week 1)

- [ ] Remove blanket `no-store` header if present

### Phase 5D: Test and Monitor (Week 2)

- [ ] Deploy to staging
- [ ] Verify edge caching: `curl -I` should show `Cache-Control` headers
- [ ] Check page load times: should drop to ~100ms on edge cache hits
- [ ] Monitor backend requests: should drop 90%+ due to edge caching

---

## Expected Outcomes

### Before ISR

```
100 users visit Morning Brief page
└── 100 full SSR requests to Cloud Run
    └── 100 Firestore reads (or API calls if cache miss)
    └── Latency: 1–3s per page view
    └── Backend load: very high
```

### After ISR + Warm Caches

```
100 users visit Morning Brief page
└── 99 served from Vercel edge cache (~100ms)
    └── 1 background revalidation to Cloud Run
    └── Cloud Run → warm Firestore cache (100ms)
└── Latency: ~100ms per page view (99th percentile)
└── Backend load: ~1% of before
```

### Metrics

| Metric | Before | After | Gain |
|--------|--------|-------|------|
| Edge cache hit ratio | 0% | 95–99% | 95–99x |
| Page load latency (p50) | 1–2s | ~100ms | 10–20x |
| Page load latency (p95) | 2–3s | ~500ms (revalidation) | 4–6x |
| Backend requests/100 users | ~100 | ~1 | 100x |
| Firestore reads/100 users | ~100 | ~1 | 100x |

---

## Rollback Plan

If ISR causes issues:

1. **Add `force-dynamic` back** to any problematic page
2. **Remove `Cache-Control` header** from any API route
3. **Restore `no-store` to vercel.json** if needed

All changes are reversible with zero data loss.

---

## Troubleshooting

### Cache-Control Headers Not Taking Effect?

1. Verify headers in response: `curl -I https://gcp3.vercel.app/api/morning-brief`
2. Check that `vercel.json` doesn't override with `no-store`
3. Clear Vercel cache: manually via dashboard if needed
4. Redeploy frontend: `vercel deploy --prod`

### ISR Revalidation Slow?

1. Verify backend cache is warm: `gcloud run services logs read gcp3-backend`
2. Check Firestore latency: ~100ms is expected
3. Verify scheduler jobs are running: `gcloud scheduler jobs list-runs`
4. If cold start: already solved by `min-instances=1` (Phase 1B)

### Pages Not Updating After Redeploy?

1. ISR revalidation is asynchronous — first user gets stale cached HTML
2. Next user (after revalidation completes) gets fresh HTML
3. Expected behavior — not a bug
4. If update is urgent, manually trigger revalidation in Vercel dashboard

---

## References

- Optimization guide: `firestore_caching_warmup_optimization.md`
- Original ISR strategy: `isr_optimization_strategy.md`
- Backend phases: `IMPLEMENTATION_GUIDE.md`
- Next.js ISR docs: https://nextjs.org/docs/basic-features/data-fetching/incremental-static-regeneration

---

**Status:** Ready to implement after Phases 1–4 backend work is verified.
