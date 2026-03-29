# GCP3 Industry Tracker — 15 Performance Optimizations

Ranked by ROI. Based on code review of the current implementation (2026-03-29).

---

## Tier 1 — Highest Impact

### 1. Remove `force-dynamic` from page routes

**Current:** Both `industry-tracker/page.tsx` and `industry-returns/page.tsx` export `force-dynamic`, which overrides the `revalidate: 3600` fetch hint. Every request triggers full SSR + backend call.

**Fix:** Replace with ISR:

```typescript
// Remove: export const dynamic = "force-dynamic"
export const revalidate = 60; // or 300 for returns page
```

**Impact:** Requests served from Vercel edge cache. Latency drops from 1-3s to ~100-300ms for cached hits. Backend load drops ~90%+.

---

### 2. Add GZipMiddleware to FastAPI

**Current:** No compression middleware. JSON payloads (~35-50 KB) sent uncompressed.

**Fix:**

```python
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

**Impact:** Payloads shrink 70-80% (to ~8-12 KB). Faster TTFB, lower bandwidth costs on Cloud Run.

---

### 3. Precompute `_attach_stored_returns()` off the request path

**Current:** Every `/industry-tracker` cache miss triggers 35-40 Firestore reads + pandas DataFrame operations per ETF (~1.5-2.5s of compute).

**Fix:** Move to a scheduled job:
- Cloud Scheduler calls `POST /admin/compute-returns` daily (or hourly)
- `/industry-tracker` reads precomputed `industry_cache` from Firestore — no live DataFrame work

**Impact:** Request latency drops by 1.5-2.5s on cache miss. Firestore read quota drops ~35-40 reads per request.

---

### 4. Split `/industry-tracker` into two endpoints

**Current:** Single endpoint returns quotes + returns + rankings + sector groupings — large payload and compute.

**Fix:**
- `GET /industry-quotes` — live prices only (lightweight, short cache)
- `GET /industry-returns` — precomputed returns + rankings (heavy, long cache)

Frontend merges via `Promise.all()`.

**Impact:** Live quotes refresh faster. Returns data cached longer. Smaller individual payloads.

---

### 5. Set Cache-Control headers on API proxy routes

**Current:** Next.js API routes return `NextResponse.json(data)` with no caching headers. Browsers and CDN can't reuse responses.

**Fix:**

```typescript
return NextResponse.json(data, {
  headers: {
    "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300",
  },
});
```

**Impact:** Vercel CDN and browsers cache responses. Repeat visits are near-instant.

---

## Tier 2 — Big Wins

### 6. Parallelize frontend data fetches

**Current:** Pages make a single heavy fetch that blocks rendering.

**Fix:** After splitting endpoints (#4), fetch in parallel:

```typescript
const [quotes, returns] = await Promise.all([
  getQuotes(),
  getReturns(),
]);
```

**Impact:** Total wait time = max(quotes, returns) instead of sum. ~30-50% faster page load.

---

### 7. Add Suspense streaming to Server Components

**Current:** Full page waits for all data before any HTML ships.

**Fix:**

```tsx
<Suspense fallback={<TableSkeleton />}>
  <IndustryTracker />
</Suspense>
```

**Impact:** Browser renders shell immediately. Users see content progressively instead of a blank screen.

---

### 8. Add `useMemo` to IndustryReturns sorting

**Current:** `IndustryTracker` correctly uses `useMemo` for sorting. `IndustryReturns` does not — it re-sorts 50 rows on every render (any state change).

**Fix:**

```typescript
const sorted = useMemo(
  () => [...data.industries].sort((a, b) => {
    const av = a.returns[sortPeriod] ?? -Infinity;
    const bv = b.returns[sortPeriod] ?? -Infinity;
    return bv - av;
  }),
  [data.industries, sortPeriod]
);
```

**Impact:** Eliminates unnecessary re-sorts. Small but free win.

---

### 9. Use edge runtime for API proxy routes

**Current:** Proxy routes run on Node.js runtime (default).

**Fix:**

```typescript
export const runtime = "edge";
```

**Impact:** ~50-150ms faster cold starts. Routes execute closer to users at Vercel edge locations.

---

### 10. Deduplicate React Server Component fetches with `cache()`

**Current:** No React `cache()` usage. If multiple components need the same data, separate fetches fire.

**Fix:**

```typescript
import { cache } from "react";

export const getData = cache(async () => {
  const res = await fetch(`${BACKEND_URL}/industry-tracker`, {
    next: { revalidate: 60 },
  });
  return res.json();
});
```

**Impact:** Guarantees one fetch per render pass regardless of how many components call `getData()`.

---

### 11. Add a global rate limiter for Finnhub requests

**Current:** Per-request semaphores exist in `data_client.py` (good), but no global request-level throttling on the FastAPI app. Under load, multiple concurrent `/industry-tracker` requests can multiply Finnhub calls.

**Fix:** Add a request-level semaphore or use `slowapi`:

```python
from asyncio import Semaphore
_INDUSTRY_LOCK = Semaphore(1)  # serialize concurrent cache-miss rebuilds

async def get_industry_data():
    async with _INDUSTRY_LOCK:
        # existing logic — only one rebuild at a time
```

**Impact:** Prevents thundering herd on cache miss. Protects Finnhub rate limits under concurrent traffic.

---

## Tier 3 — Advanced

### 12. Compact payload mode

**Current:** All 50 industries x 13 return periods + enrichment fields sent on every request (~35-50 KB).

**Fix:** Support a `?view=compact` query param that returns only essential fields (price, change_pct, sector). Full data on demand via `?view=full`.

**Impact:** Initial payload drops to ~8-12 KB (uncompressed). Faster parse, less memory, better mobile experience.

---

### 13. Client-side table virtualization

**Current:** Full DOM rendering of 50 rows x many columns. Not a bottleneck yet, but becomes one if the table grows or runs on low-end mobile devices.

**Fix:** Use `@tanstack/react-virtual` for windowed rendering.

**Impact:** DOM node count drops from ~1000+ to ~50-100 visible. Smoother scrolling, lower memory.

---

### 14. Stale-while-revalidate UX pattern

**Current:** Page shows nothing until fresh data arrives.

**Fix:** Cache last-known data client-side (localStorage or SWR/React Query) and show it immediately while fresh data loads in the background.

**Impact:** Perceived instant load. Users see data within milliseconds, updated silently when the fetch completes.

---

### 15. Remove Alpha Vantage from default enrichment path

**Current:** AV enrichment runs on `/industry-tracker` if quota allows. It's quota-aware and non-blocking (good), but adds latency when it fires and provides limited value (1-month return, mean/stddev).

**Fix:** Move AV enrichment to the scheduled precompute job (#3) or a separate `POST /admin/enrich-av` endpoint. Remove from the live request path entirely.

**Impact:** Eliminates 10 AV API calls (batched) from live requests. Simplifies the hot path. AV data still available — just precomputed.

---

## Quick Reference

| # | Optimization | Effort | Impact | Where |
|---|-------------|--------|--------|-------|
| 1 | Remove force-dynamic | 5 min | Very High | Frontend pages |
| 2 | GZipMiddleware | 5 min | High | Backend main.py |
| 3 | Precompute returns | 2-4 hr | Very High | Backend industry.py |
| 4 | Split endpoint | 2-3 hr | High | Backend + frontend |
| 5 | Cache-Control headers | 15 min | High | Frontend API routes |
| 6 | Parallel fetches | 30 min | Medium | Frontend pages |
| 7 | Suspense streaming | 30 min | Medium | Frontend pages |
| 8 | useMemo IndustryReturns | 5 min | Low | Frontend component |
| 9 | Edge runtime | 5 min | Medium | Frontend API routes |
| 10 | React cache() | 15 min | Low-Med | Frontend data layer |
| 11 | Global rate limiter | 1 hr | Medium | Backend |
| 12 | Compact payload | 1-2 hr | Medium | Backend + frontend |
| 13 | Table virtualization | 1-2 hr | Low-Med | Frontend component |
| 14 | Stale-while-revalidate | 1-2 hr | Medium | Frontend UX |
| 15 | Move AV off hot path | 1 hr | Low-Med | Backend industry.py |

---

**Document Version:** 1.0
**Last Updated:** 2026-03-29
**No secrets or credentials are included in this document.**
