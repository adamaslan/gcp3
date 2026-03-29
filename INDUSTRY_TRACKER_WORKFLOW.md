# Industry Tracker: End-to-End Workflow

**Date**: 2026-03-29
**Project**: your-project-id
**Environment**: Cloud Run / us-central1

---

## Overview

The industry tracker monitors 50 ETFs across 9 sectors. It uses a two-collection Firestore strategy: `etf_history` for permanent price storage and `industry_cache` for computed returns. After the initial seed, live API calls are limited to real-time quotes only — all return calculations run locally from stored history.

---

## Phase 1: Seed `etf_history` (one-time, then daily)

Run from the backend directory with the `fin-ai1` mamba environment active:

```bash
source /opt/homebrew/Caskroom/miniforge/base/etc/profile.d/conda.sh && \
source /opt/homebrew/Caskroom/miniforge/base/etc/profile.d/mamba.sh && \
mamba activate fin-ai1 && \
GCP_PROJECT_ID=your-project-id FINNHUB_API_KEY=your-finnhub-api-key \
python backend/seed_and_report.py
```

**What happens:**

```
For each of 50 unique ETFs (sorted alphabetically):
  1. Finnhub /stock/candle — PRIMARY
       1-year daily OHLCV (free tier max)
       120ms between requests → ~8 req/s
       429 handling: 3s sleep + 1 retry
       → etf_store.store_history() or append_daily()

  2. yfinance period="max" — FALLBACK (only if Finnhub returns empty)
       Full ETF inception history
       4s delay between fallback attempts
       Browser User-Agent set to reduce bot-detection risk
       → etf_store.store_history() or append_daily()

Output: CSV to stdout, logs to stderr
```

**CSV output:**

```
symbol,action,source,rows_stored,first_date,last_date,total_days,status
IGV,full_seed,finnhub,365,2025-03-29,2026-03-28,365,ok
SOXX,full_seed,finnhub,365,2025-03-29,2026-03-28,365,ok
CLOU,full_seed,yfinance,4200,2014-01-01,2026-03-28,4200,ok
```

**After this step:** `etf_history` is populated. `industry_cache` is still **empty**.

---

## Phase 2: First `/industry-tracker` Request

This is the step that wires `etf_history` → `industry_cache`. Must be run after seeding.

```
GET /industry-tracker
  │
  ├─ 1. Check gcp3_cache → miss on first run
  │
  ├─ 2. Fetch live quotes for all 50 ETFs concurrently
  │      Finnhub /quote (primary, semaphore 25 + 50ms stagger)
  │      → yfinance fallback per symbol on failure
  │
  ├─ 3. Alpha Vantage enrichment (if daily quota allows)
  │      Batches of 5 ETFs per call (free tier max = 25 calls/day)
  │      Returns: cumulative_return, mean, stddev (1-month window only)
  │      Skipped silently if quota exhausted — never blocks quotes
  │
  ├─ 4. _attach_stored_returns()  ← POPULATES industry_cache
  │      For each unique ETF:
  │        load_history() from etf_history Firestore
  │        compute_returns() locally — 13 periods + 52w high/low
  │      Batch-writes all 50 industries → industry_cache collection
  │
  ├─ 5. Write full result → gcp3_cache (TTL 24h)
  │
  └─ Returns: quotes + returns + rankings + by_sector leaders/laggards
```

**Trigger manually after seeding:**

```bash
curl https://your-cloud-run-url/industry-tracker
```

---

## Phase 3: `/industry-returns` — Zero API Calls

Only works after Phase 2 has run at least once.

```
GET /industry-returns
  │
  ├─ Check gcp3_cache (key: industry_returns:YYYY-MM-DD) → TTL 6h
  │    Hit? → return immediately
  │
  └─ Read all docs from industry_cache collection
       Rank each of 13 periods → top 5 leaders / bottom 5 laggards
       Write result → gcp3_cache (TTL 6h)
       Returns: {industries[], leaders{}, laggards{}, periods_available[]}
```

**Return periods available:** `1d, 3d, 1w, 2w, 3w, 1m, 3m, 6m, ytd, 1y, 2y, 5y, 10y`

---

## Phase 4: Daily Delta (keep data current)

Run after market close on weekdays (~6 PM ET):

```
1. seed_and_report.py (or POST /admin/seed-etf-history)
     etf_store.append_daily() — only rows newer than last_date stored
     etf_history updated. industry_cache still shows yesterday's returns.

2. Next GET /industry-tracker call refreshes industry_cache automatically
     (or trigger explicitly)
```

**HTTP trigger (Cloud Scheduler):**

```
POST /admin/seed-etf-history
X-Scheduler-Token: your-scheduler-token
```

Note: This path uses yfinance only (no Finnhub), no rate-limit session, no CSV report.

---

## Data Dependency Map

```
seed_and_report.py
  └─ writes ──→ etf_history/{SYMBOL}
                       │
                       ▼
GET /industry-tracker
  └─ _attach_stored_returns()
       reads etf_history → computes returns
         └─ writes ──→ industry_cache/{Industry Name}
                               │
                               ▼
                   GET /industry-returns reads here
                   (0 API calls, 0 etf_store reads)
```

---

## Critical Ordering Rule

```
seed_and_report.py   →   GET /industry-tracker   →   GET /industry-returns
     (writes                  (writes                    (reads
   etf_history)            industry_cache)             industry_cache)
```

Skipping the middle step means `/industry-returns` returns empty results.

---

## API Quota Summary

| Source | Limit | Role |
|--------|-------|------|
| Finnhub | 60 calls/min | Live quotes + seed (primary) |
| yfinance | ~100–200 req/min IP-based | Quote fallback + seed fallback |
| Alpha Vantage | 25 calls/day hard cap | Returns enrichment only (bonus) |
| Firestore | 50k reads / 20k writes per day free | All storage — fits free tier |

---

---

## Next.js Frontend Implementation

### Request flow

```
Browser
  │
  ├─ /industry-tracker page (Server Component, force-dynamic)
  │    getData() → fetch BACKEND_URL/industry-tracker { revalidate: 3600 }
  │    → renders <IndustryTracker data={data} />
  │
  └─ /industry-returns page (Server Component, force-dynamic)
       getData() → fetch BACKEND_URL/industry-returns { revalidate: 3600 }
       → renders <IndustryReturns data={data} />
```

Both pages use `export const dynamic = "force-dynamic"` — no static generation, always SSR. The `revalidate: 3600` hint is advisory for Next.js ISR but has no effect when `force-dynamic` is set.

### API proxy routes

API routes in `src/app/api/` proxy directly to `BACKEND_URL` with no transformation:

| Route | Revalidate | Backend endpoint |
|-------|-----------|-----------------|
| `/api/industry-tracker` | 3600s | `BACKEND_URL/industry-tracker` |
| `/api/industry-returns` | 21600s | `BACKEND_URL/industry-returns` |

Both return 503 on network error or non-OK backend response. `BACKEND_URL` is a required server-side env var — missing it returns HTTP 500.

### `IndustryTracker` component (`"use client"`)

Receives the full backend payload as props from the Server Component. All interactivity is client-side state only — no further fetches after initial load.

**UI state:**
- `view`: `"ranked"` (all 50 sorted by selected period) | `"sector"` (grouped by sector)
- `showReturns`: toggles the 13-period return columns in the table
- `leaderPeriod`: which period drives the Top Leaders / Top Laggards panels

**Conditional columns — only render when data is present:**
- `return_1m`, `mean_daily_return`, `stddev_daily` — shown only when Alpha Vantage enrichment ran (checked via `hasEnrichment()`)
- 13 return period columns + 52W Hi/Lo — shown only when `etf_history` has been seeded (checked via `hasStoredReturns()`)

**Unseeded state notice:**
```
52W Hi/Lo and multi-period returns require ETF history to be seeded.
Run POST /admin/seed-etf-history once to populate.
```
This banner renders automatically when `hasStoredReturns()` returns false.

**Sort:** Any column is sortable. Clicking the active column toggles asc/desc. Nulls always sort last. Computed via `useMemo` — no re-fetches.

**Period selector for leaders/laggards panel:**
- `1d` uses live `change_pct` from Finnhub/yfinance quote
- All other periods use `row.returns[period]` from `etf_history` — disabled (grayed out) until seeded

### `IndustryReturns` component (`"use client"`)

Dedicated multi-period returns view, sourced from `industry_cache` (zero API calls at render time).

**UI state:**
- `sortPeriod`: which period column is active (default `1m`)
- `view`: `"top"` (top 10) | `"bottom"` (bottom 10) | `"all"` (all 50)
- `show52w`: toggles 52W Hi/Lo columns

**Data shape expected from backend:**
```typescript
{
  date: string;
  total: number;
  industries: { etf, industry, returns: {1d..10y}, 52w_high, 52w_low }[];
  leaders:  Record<period, { industry, etf, return }[]>;  // top 5 per period
  laggards: Record<period, { industry, etf, return }[]>;  // bottom 5 per period
  periods_available: string[];
}
```

**Color scale for return values:**
- `>= +5%` → `text-green-300`
- `>= +1%` → `text-green-500`
- `>= 0%`  → `text-green-700`
- `>= -1%` → `text-red-700`
- `>= -5%` → `text-red-500`
- `< -5%`  → `text-red-300`

### Environment variables

| Var | Where set | Used by |
|-----|-----------|---------|
| `BACKEND_URL` | Vercel env / Cloud Run | All API proxy routes + page Server Components |
| `FINNHUB_API_KEY` | Cloud Run Secret Manager | Backend only — never in frontend |

---

## Relevant Files

| File | Role |
|------|------|
| `backend/seed_and_report.py` | CLI seed — writes `etf_history`, Finnhub primary / yfinance fallback |
| `backend/etf_store.py` | `store_history`, `append_daily`, `compute_returns` |
| `backend/industry.py` | Live quotes + `_attach_stored_returns` → `industry_cache` |
| `backend/industry_returns.py` | Reads `industry_cache`, ranks by period |
| `backend/data_client.py` | Finnhub, yfinance, AV clients + rate-limit logic |
| `backend/firestore.py` | Firestore client singleton |
| `frontend/src/app/industry-tracker/page.tsx` | Server Component — fetches + passes to `IndustryTracker` |
| `frontend/src/app/industry-returns/page.tsx` | Server Component — fetches + passes to `IndustryReturns` |
| `frontend/src/app/api/industry-tracker/route.ts` | API proxy → `BACKEND_URL/industry-tracker` |
| `frontend/src/app/api/industry-returns/route.ts` | API proxy → `BACKEND_URL/industry-returns` |
| `frontend/src/components/IndustryTracker.tsx` | Client component — quotes table, leaders/laggards, period selector |
| `frontend/src/components/IndustryReturns.tsx` | Client component — multi-period returns table, sortable |

---

**Document Version:** 1.1
**Last Updated:** 2026-03-29
**API Key**: [REDACTED — set via `FINNHUB_API_KEY` in Cloud Run Secret Manager]
