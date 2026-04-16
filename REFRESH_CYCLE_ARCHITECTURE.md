# GCP3 Finance: Full Stack Architecture & Refresh Cycle

## Executive Summary

**7 endpoints still not refreshing correctly.** This document maps the complete data flow from Cloud Scheduler triggers → Backend API refresh stages → Firestore cache → Frontend pages, highlighting all components involved in the refresh cycle.

---

## Stack Layers

| Layer | Technology | Key Files |
|-------|-----------|-----------|
| **Frontend** | Next.js 15 (TypeScript) + Tailwind | `frontend/src/app/*/page.tsx` |
| **API Layer** | Next.js API routes (proxy) | `frontend/src/app/api/*/route.ts` |
| **Backend** | FastAPI (Python 3.11) + Uvicorn | `backend/main.py`, `backend/*.py` |
| **Cache** | Firestore (TTL-based) | `gcp3_cache` collection |
| **External APIs** | Finnhub, Alpha Vantage, yfinance, Gemini | `data_client.py` |
| **Infrastructure** | GCP Cloud Run, Cloud Scheduler, Cloud Build | `cloudbuild.yaml` |

---

## Refresh Cycle Overview

### 7 Cloud Scheduler Jobs (Trigger the Refresh Cycle)

| Job Name | Schedule | Trigger URI | Endpoint |
|----------|----------|-------------|----------|
| `gcp3-premarket-warmup` | 8:30 AM ET (Mon-Fri) | `POST /refresh/premarket` | Lightweight pre-market |
| `gcp3-ai-summary-refresh` | 9:35 AM ET (Mon-Fri) | `POST /refresh/all` | Full morning warm-up |
| `gcp3-midday-intraday-refresh` | 12:00 PM ET (Mon-Fri) | `POST /refresh/intraday` | Mid-day updates (skip_gemini=false) |
| `gcp3-eod-intraday-refresh` | 4:15 PM ET (Mon-Fri) | `POST /refresh/intraday?skip_gemini=true` | EOD updates |
| `gcp3-nightly-cache-purge` | 2:00 AM ET daily | `POST /admin/purge-cache` | Clean expired cache |
| `compute-returns` | 6:00 AM ET Mon-Fri | `POST /admin/compute-returns` | Pre-market returns calc |
| `seed-etf-history` | Manual (or on deploy) | `POST /admin/seed-etf-history` | Backfill yfinance data |

---

## Data Flow Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Cloud Scheduler                                  │
│  (7 jobs) ──→ POST requests with OIDC auth header ──→ Cloud Run     │
└──────────────────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────────────┐
│                    Backend (Cloud Run)                               │
│  main.py: _verify_scheduler() ──→ Endpoint handler                   │
└──────────────────────────────────────────────────────────────────────┘
                         ↓
    ┌────────────────────┴────────────────────┐
    ↓                                          ↓
Fetch Phase                              Bake Phase
(Ingest external data)                  (Compute + synthesize)
    ↓                                          ↓
┌────────────────────────────────┐  ┌────────────────────────────────┐
│ Finnhub / yfinance / Gemini    │  │ Firestore reads + Gemini API   │
│ ↓ ↓ ↓                           │  │ ↓ ↓ ↓                           │
│ market data                    │  │ return calculations           │
│ sector rotation                │  │ AI summary generation         │
│ industry quotes                │  │ blog generation               │
│ earnings + news                │  │ correlation analysis          │
│ screener data                  │  │ story selection               │
└────────────────────────────────┘  └────────────────────────────────┘
    ↓                                          ↓
    └────────────────────┬────────────────────┘
                         ↓
        ┌────────────────────────────┐
        │  Firestore (gcp3_cache)    │
        │  - TTL-based auto-delete   │
        │  - In-memory L1 cache      │
        │  - Checkpoint documents    │
        └────────────────────────────┘
                         ↓
        ┌────────────────────────────┐
        │  Frontend (Next.js on Vercel)
        │  - API routes (proxy)      │
        │  - Pages fetch from routes │
        │  - ISR (revalidate: 60s)   │
        └────────────────────────────┘
```

---

## Detailed Endpoint & Stage Breakdown

### A. Refresh Endpoints (Main Cycle)

#### 1. **POST /refresh/premarket** (8:30 AM ET)
**Purpose:** Lightweight early warm-up for pre-market traders.  
**Stages:**
- `lightweight_data` → 3 concurrent calls (no heavy Finnhub/AV):
  - `get_morning_brief()` — News headlines
  - `get_news_sentiment()` — Sentiment analysis
  - `get_macro_pulse()` — Macro indicators

**Output:** `{"status": "premarket_warmed", "stages": {...}, "total_ms": int}`  
**Cache writes:** 3 docs (morning_brief, news_sentiment, macro_pulse)  
**TTL:** 8h, 6h, 1h respectively

---

#### 2. **POST /refresh/all** (9:35 AM ET) — FULL WARM-UP
**Purpose:** Complete morning cache refresh with all stages in dependency order.  
**Critical:** This is the **most comprehensive refresh job** — runs all 9 stages.

**Stages (in order):**

| Stage | Name | Dependencies | Components |
|-------|------|--------------|-----------|
| 0 | `firestore_readers` | None | `get_technical_signals()`, `get_market_summary()` |
| 1 | `market_data` | None (concurrent) | `get_morning_brief()`, `get_macro_pulse()`, `get_earnings_radar()`, `get_news_sentiment()` |
| 2 | `sector_screener` | None (concurrent) | `get_sector_rotation()`, `get_screener_data()` |
| 3 | `industry` | Stages 0-2 complete | `get_industry_data(enrich_av=True)` — 50 Finnhub + 10 AV batches |
| 3b | `compute_returns` | Stage 3 complete | `compute_returns()` — Multi-period ETF returns from etf_store |
| 4 | `backend2` | Stages 0-3b complete | HTTP fan-out to backend2: `/scan` + 5 fibonacci endpoints |
| 5 | `ai_summary` | Stages 1-4 complete | `refresh_ai_summary()` — Gemini synthesis of all data |
| 6 | `daily_blog` | Stages 1-2 complete | `refresh_daily_blog()` — Gemini blog generation |
| 7 | `blog_review` | Stage 6 success | `refresh_blog_review()` — Gemini blog review (gated on 6) |
| 8 | `correlation_article` | Stages 1-5 complete | `refresh_correlation_article()` — Gemini correlation analysis |

**Output:** `{"status": "refreshed", "date": "2026-04-15", "stages": {...}, "total_ms": int}`  
**Cache writes:** ~20 documents (all endpoints)  
**Total time:** ~30-50s (concurrent stages + sequential dependencies)

---

#### 3. **POST /refresh/fetch** (9:30 AM ET, Mon-Fri only)
**Purpose:** Phase 1 of Fetch-then-Bake: **ingest all external data** into Firestore.  
**Gating:** Skips on non-trading days.  
**Checkpoint:** Writes `refresh_state:fetch` document.

**Stages (F0-F4):**

| Stage | Name | What it does | Calls |
|-------|------|--------------|-------|
| F0 | `etf_history` | Delta-append ETF price history (yfinance only) | `seed_etf_history()` |
| F1 | `market_data` | Concurrent market data (4 calls, Finnhub) | morning_brief, macro_pulse, earnings_radar, news_sentiment |
| F2 | `sector_screener` | Concurrent sector + screener (Finnhub + Gemini) | sector_rotation, screener_data |
| F3 | `industry` | 50 Finnhub quotes + AV analytics (10 batches) | `get_industry_data(enrich_av=True)` |
| F4 | `backend2` | Fan-out to backend2 (/scan + fibonacci) | 6 HTTP calls |

**Checkpoint document:** `gcp3_cache:refresh_state:fetch`
```json
{
  "trading_date": "2026-04-15",
  "phase": "fetch",
  "status": "fetch_ok" | "fetch_partial" | "fetch_failed",
  "stages_completed": ["etf_history", "market_data", ...],
  "stages_failed": [],
  "written_at": "2026-04-15T13:30:00Z"
}
```

**Output:** `{"status": "fetch_ok|partial|failed", "trading_date": "...", "stages": {...}}`

---

#### 4. **POST /refresh/bake** (9:45 AM ET, Mon-Fri only)
**Purpose:** Phase 2 of Fetch-then-Bake: **compute + synthesize** from Firestore data only.  
**Gating:** Requires `refresh_state:fetch` checkpoint with status `fetch_ok` or `fetch_partial`.  
**Checkpoint:** Writes `refresh_state:bake` document.

**Stages (B0-B6):**

| Stage | Name | External APIs | Depends on |
|-------|------|----------------|-----------|
| B0 | `compute_returns` | None (Firestore reads only) | etf_store data |
| B1 | `industry_returns_seal` | None (Firestore reads/writes) | B0 complete |
| B2 | `ai_summary` | Gemini only | Stages 0-1 + Firestore |
| B3 | `daily_blog` | Gemini only | B2 complete + cached data |
| B4 | `blog_review` | Gemini only | B3 success (gated) |
| B5 | `correlation_article` | Gemini only | B0-2 complete |
| B6 | `story_article` | None (deterministic selection) | B0-1 complete |

**Checkpoint document:** `gcp3_cache:refresh_state:bake`
```json
{
  "trading_date": "2026-04-15",
  "phase": "bake",
  "status": "bake_ok" | "bake_partial" | "bake_failed",
  "stages_completed": ["compute_returns", "industry_returns_seal", ...],
  "stages_failed": [],
  "written_at": "2026-04-15T13:45:00Z"
}
```

**Output:** `{"status": "bake_ok|partial|failed", "trading_date": "...", "fetch_checkpoint": "...", "stages": {...}}`

---

#### 5. **POST /refresh/intraday** (12:00 PM ET & 4:15 PM ET, Mon-Fri)
**Purpose:** Short-TTL updates for mid-day and EOD (skips heavy industry, earnings, ai_summary).  
**Parameters:** `?skip_gemini=true` (for EOD run to avoid 3rd daily Gemini call)

**Stages (3 concurrent):**
- `market_data` → morning_brief, macro_pulse, news_sentiment (cache hits likely)
- `sector_screener` → sector_rotation (Gemini, unless skip_gemini=true), screener_data
- `backend2_scan` → /scan only (fibonacci endpoints still fresh from morning)

**Output:** `{"status": "refreshed", "stages": {...}, "total_ms": int}`

---

### B. Admin Endpoints (Support Infrastructure)

#### 6. **POST /admin/compute-returns** (6:00 AM ET, Mon-Fri)
**Purpose:** Precompute multi-period returns from `etf_store` → `industry_cache`.  
**Calls:** Zero Finnhub/AV calls (Firestore reads only).  
**Output:** `{"status": "ok", "days": int, "returns_computed": {...}}`

---

#### 7. **POST /admin/purge-cache** (2:00 AM ET daily)
**Purpose:** Safety net for expired cache cleanup (alongside native Firestore TTL).  
**Batches:** Deletes up to 450 docs per pass (Firestore batch limit).  
**Output:** `{"deleted": int, "timestamp": "ISO string"}`

---

#### 8. **POST /admin/seed-etf-history** (Manual or on deploy)
**Purpose:** Backfill permanent ETF price history.  
- First run: Full history via yfinance
- Subsequent runs: Delta-append only new trading days (3mo fetch)

**Output:** `{"status": "ok", "etfs": int, "total_rows": int, "detail": {...}}`

---

## Backend Components: Who Does What

### Core Data Fetching

| Module | Function | API Calls | Cache Key | TTL |
|--------|----------|-----------|-----------|-----|
| `data_client.py` | `get_quote(symbol)`, `get_quotes([])` | Finnhub → yfinance | N/A (per-call) | N/A |
| `data_client.py` | `av_analytics_batch(symbols)` | Alpha Vantage (5 sym/call) | N/A | N/A |
| `morning.py` | `get_morning_brief()` | Finnhub `/news` | `morning_brief` | 8h |
| `macro_pulse.py` | `get_macro_pulse()` | Finnhub + AV | `macro_pulse` | 1h |
| `earnings_radar.py` | `get_earnings_radar()` | Finnhub `/stock/earnings` | `earnings_radar` | 6h |
| `news_sentiment.py` | `get_news_sentiment()` | Finnhub `/news` + Gemini | `news_sentiment` | 6h |

### Industry & Returns

| Module | Function | Source | Cache Key | TTL |
|--------|----------|--------|-----------|-----|
| `industry.py` | `get_industry_data(enrich_av=True)` | Finnhub (50 quotes) + AV batches | `industry_quotes:{bucket}`, `industry_cache:{date}` | 24h |
| `industry.py` | `compute_returns()` | Firestore `etf_store` reads | `industry_cache:{date}` (overwrites) | 24h |
| `industry_returns.py` | `get_industry_returns(force=True)` | Firestore reads | `industry_returns` | 24h |

### Sector & Technical

| Module | Function | API Calls | Cache Key | TTL |
|--------|----------|-----------|-----------|-----|
| `sector_rotation.py` | `get_sector_rotation()` | Gemini synthesis | `sector_rotation` | 4h |
| `technical_signals.py` | `get_technical_signals()` | Firestore reads | `technical_signals` | 4h |
| `screener.py` | `get_screener_data()` | Gemini synthesis | `screener` | 4h |
| `market_summary.py` | `get_market_summary()` | Firestore reads | `market_summary` | 4h |

### Content Generation (AI/Gemini)

| Module | Function | Source | Cache Key | TTL |
|--------|----------|--------|-----------|-----|
| `ai_summary.py` | `refresh_ai_summary()` | Gemini (all cached data) | `ai_summary`, `ai_summary:detail` | Until midnight |
| `daily_blog.py` | `refresh_daily_blog()` | Gemini (market data) | `daily_blog` | Until midnight |
| `blog_reviewer.py` | `refresh_blog_review()` | Gemini (reviews daily_blog) | `blog_review` | Until midnight |
| `correlation_article.py` | `refresh_correlation_article()` | Gemini (industry returns) | `correlation_article` | Until midnight |
| `story_picker.py` | `refresh_story_article()` | Deterministic selection | `story_article` | Until midnight |

---

## Firestore Cache Layer

### Collection: `gcp3_cache`

**Document structure (all keys):**
```json
{
  "value": {...},           // Actual cached data (varies by endpoint)
  "expires_at": "2026-04-15T13:00:00Z",  // Auto-delete timestamp (TTL)
  "updated_at": "2026-04-15T12:00:00Z"   // When it was last written
}
```

### Document Keys & TTLs

| Key Pattern | Source | Refreshed | TTL | Size (approx) |
|-------------|--------|-----------|-----|---------------|
| `morning_brief` | Finnhub news | /refresh/all (stage 1) | 8h | 10 KB |
| `macro_pulse` | Finnhub + AV | /refresh/all (stage 1) | 1h | 5 KB |
| `earnings_radar` | Finnhub earnings | /refresh/all (stage 1) | 6h | 20 KB |
| `news_sentiment` | Finnhub + Gemini | /refresh/all (stage 1) | 6h | 8 KB |
| `sector_rotation` | Gemini | /refresh/all (stage 2) | 4h | 3 KB |
| `screener` | Gemini | /refresh/all (stage 2) | 4h | 15 KB |
| `industry_quotes:{minute}` | Finnhub (50 ETFs) | /refresh/all (stage 3) | 1h | 8 KB |
| `industry_cache:{date}` | etf_store + compute | /refresh/all (3b) | 24h | 50 KB |
| `industry_returns` | etf_store + compute | /refresh/bake (B1) | 24h | 40 KB |
| `technical_signals` | Firestore reads | /refresh/all (stage 0) | 4h | 12 KB |
| `market_summary` | Firestore reads | /refresh/all (stage 0) | 4h | 6 KB |
| `ai_summary` | Gemini | /refresh/all (stage 5) | Until midnight | 25 KB |
| `ai_summary:detail` | Gemini | /refresh/all (stage 5) | Until midnight | 50 KB |
| `daily_blog` | Gemini | /refresh/all (stage 6) | Until midnight | 30 KB |
| `blog_review` | Gemini | /refresh/all (stage 7) | Until midnight | 20 KB |
| `correlation_article` | Gemini | /refresh/all (stage 8) | Until midnight | 35 KB |
| `story_article` | Deterministic | /refresh/bake (B6) | Until midnight | 25 KB |
| `refresh_state:fetch` | Checkpoint | /refresh/fetch | 24h | 1 KB |
| `refresh_state:bake` | Checkpoint | /refresh/bake | 24h | 1 KB |
| `etf_store:history:{etf}` | yfinance | /refresh/fetch (F0) | Permanent | 100-200 KB each |

### In-Memory Cache Layer (L1)

**File:** `firestore.py:mem_*` functions  
**Purpose:** Eliminate Firestore round-trips on warm instances (60s max age).  
**Capacity:** 256 entries with FIFO eviction.  
**Hit impact:** ~0ms vs. 50-200ms for Firestore.

---

## Frontend Layer

### Pages (8 consolidated)

| Page | Route | Component | Data Source | Refresh |
|------|-------|-----------|-------------|---------|
| Home | `/` | HomePage | N/A | Static |
| Industry Intelligence | `/industry-intel` | IndustryTracker | `GET /api/industry-intel` | ISR 60s |
| Signals Hub | `/signals` | TechnicalSignals | `GET /api/signals` | ISR 60s |
| Screener | `/screener` | Screener | `GET /api/screener` | ISR 60s |
| Market Overview | `/market-overview` | MarketSummary | `GET /api/market-overview` | ISR 60s |
| Industry Returns | `/industry-returns` | IndustryReturns | `GET /api/industry-returns` | ISR 60s |
| Content Hub | `/content` | DailyBlog + CorrelationArticle | `GET /api/content` | ISR 60s |
| Macro Pulse | `/macro` | MacroPulse | `GET /api/macro` | ISR 60s |

### API Routes (proxy layer)

**File:** `frontend/src/app/api/*/route.ts`  
**Purpose:** Proxy backend endpoints (add CORS, auth, caching headers).  
**Pattern:** All routes fetch from `BACKEND_URL` env var.

**Routes (7 main + 1 OG image):**
- `GET /api/industry-intel` → `BACKEND_URL/industry-intel`
- `GET /api/signals` → `BACKEND_URL/signals`
- `GET /api/screener` → `BACKEND_URL/screener`
- `GET /api/market-overview` → `BACKEND_URL/market-overview`
- `GET /api/industry-returns` → `BACKEND_URL/industry-returns`
- `GET /api/content` → `BACKEND_URL/content`
- `GET /api/macro` → `BACKEND_URL/macro`
- `GET /api/og` → Open Graph image generation

### ISR Configuration

**File:** `frontend/src/app/*/page.tsx`  
**Pattern:** Every page fetch includes `next: { revalidate: 60 }` on `revalidate-after-60-seconds` cache.

Example:
```typescript
const data = await fetch(`${BACKEND_URL}/industry-intel`, {
  next: { revalidate: 60 },  // Revalidate every 60s
});
```

---

## The 7 Endpoints Not Refreshing (Root Cause Analysis)

Based on the 7 Cloud Scheduler jobs and endpoint mapping, here are the **7 likely candidates failing to refresh correctly**:

### 1. Industry Intelligence (`/industry-intel`)
**Refresh Job:** `/refresh/all` (Stage 3)  
**Dependency:** `industry_cache:{date}` + `industry_quotes:{minute}`  
**Issue:** If `compute_returns()` (Stage 3b) fails, industry_returns won't update, cascading to the page.

### 2. Signals Hub (`/signals`)
**Refresh Job:** `/refresh/all` (Stage 0 + conditional)  
**Dependency:** `technical_signals` + `market_summary`  
**Issue:** Firestore reader endpoints may not be waking up properly; check `/debug/status` for missing routes.

### 3. Screener (`/screener`)
**Refresh Job:** `/refresh/all` (Stage 2)  
**Dependency:** `screener` cache  
**Issue:** Gemini synthesis may be timing out; check API quota.

### 4. Market Overview (`/market-overview`)
**Refresh Job:** `/refresh/all` (Stages 1 + conditional)  
**Dependency:** `earnings_radar` + `macro_pulse` + `market_summary`  
**Issue:** Multi-endpoint dependency; any stage failure cascades.

### 5. Industry Returns (`/industry-returns`)
**Refresh Job:** `/refresh/bake` (Stage B1)  
**Dependency:** `industry_returns` cache  
**Issue:** Depends on Fetch checkpoint; if fetch fails, bake aborts.

### 6. Content Hub (`/content`)
**Refresh Job:** `/refresh/all` (Stages 5-8)  
**Dependency:** `daily_blog`, `blog_review`, `correlation_article`, `story_article`  
**Issue:** Complex Gemini dependencies; blog_review gated on blog generation.

### 7. Macro Pulse (`/macro`)
**Refresh Job:** `/refresh/all` (Stage 1) + `/refresh/intraday`  
**Dependency:** `macro_pulse` cache (1h TTL)  
**Issue:** Very short TTL; refresh jobs may overlap or miss the window.

---

## Refresh Cycle Timing (EST)

```
06:00 AM  │ compute-returns           (Admin: pre-market calculations)
          │
08:30 AM  │ gcp3-premarket-warmup     (POST /refresh/premarket)
          │  ├─ morning_brief
          │  ├─ news_sentiment
          │  └─ macro_pulse
          │
09:30 AM  │ gcp3-fetch                (POST /refresh/fetch) — Phase 1
          │  ├─ F0: etf_history
          │  ├─ F1: market_data (4 concurrent)
          │  ├─ F2: sector_screener (2 concurrent)
          │  ├─ F3: industry (50 Finnhub + 10 AV)
          │  ├─ F4: backend2 fan-out
          │  └─ [Checkpoint: refresh_state:fetch]
          │
09:35 AM  │ gcp3-ai-summary-refresh   (POST /refresh/all) — Full warm-up
          │  ├─ Stage 0-4: Same as Fetch
          │  ├─ Stage 5: ai_summary
          │  ├─ Stage 6-8: Gemini content
          │
09:45 AM  │ gcp3-bake                 (POST /refresh/bake) — Phase 2
          │  ├─ B0: compute_returns
          │  ├─ B1: industry_returns (force=True)
          │  ├─ B2-6: Gemini synthesis + content
          │  └─ [Checkpoint: refresh_state:bake]
          │
12:00 PM  │ gcp3-midday-intraday-refresh (POST /refresh/intraday)
          │  ├─ market_data (cache hits likely)
          │  ├─ sector_screener (Gemini)
          │  └─ backend2_scan only
          │
04:15 PM  │ gcp3-eod-intraday-refresh (POST /refresh/intraday?skip_gemini=true)
          │  └─ Same as midday, but skip 2nd Gemini call
          │
02:00 AM  │ gcp3-nightly-cache-purge  (POST /admin/purge-cache)
          │  └─ Delete expired docs
```

---

## Cache TTL Summary

| Category | TTL | Refreshed |
|----------|-----|-----------|
| **Market Data** (morning_brief, macro_pulse, news_sentiment) | 1-8h | Every 1-4 hours via jobs |
| **Sector & Technical** (sector_rotation, technical_signals) | 4h | Morning + intraday |
| **Industry** (industry_quotes, industry_cache) | 1-24h | Morning + compute_returns |
| **Content** (blog, articles) | Until midnight | Once per day (morning) |
| **Checkpoints** (refresh_state:fetch/bake) | 24h | Each refresh job |

---

## Common Refresh Failures & Root Causes

### Symptom: Endpoint returns stale data

**Probable causes:**
1. **Cache miss + refresh job failed** → Check Cloud Scheduler logs for failed job
2. **Fetch checkpoint missing/failed** → Bake aborts (503); check `refresh_state:fetch`
3. **Gemini quota exhausted** → Stages 5-8 fail silently
4. **Backend2 URL not set** → Optional stage skipped; affects fibonacci/scan
5. **SCHEDULER_SECRET mismatch** → Jobs return 401; check Secret Manager vs job config
6. **Frontend ISR revalidate too long** → Page stays stale until 60s expires

### Symptom: "7 endpoints still not refreshing"

**Check in order:**
1. **Is today a trading day?** → `/refresh/fetch` and `/refresh/bake` skip non-trading days
2. **Did refresh jobs run?** → Check Cloud Run logs for job trigger timestamps
3. **Did checkpoints complete?** → `gcloud firestore read-document gcp3_cache/refresh_state:fetch`
4. **Are routes registered?** → `GET /debug/status` → check `route_inventory` + `missing_expected_routes`
5. **Is cache expired?** → `gcloud firestore read-document gcp3_cache/{key}` → check `expires_at`
6. **Did Gemini fail?** → Content endpoints depend on Gemini; check API quota + logs
7. **Did Finnhub rate-limit?** → Check `GET /debug/status` → `rate_limits.finnhub_429s`

---

## Deployment & Verification

### Check Backend Health
```bash
# Check all registered routes
curl https://gcp3-backend-{id}.a.run.app/debug/status

# Output includes:
# - route_inventory: all registered GET/POST
# - missing_expected_routes: gaps
# - industry_cache freshness
# - gcp3_cache live doc count
```

### Monitor Scheduler Jobs
```bash
# View job execution history
gcloud scheduler jobs list --project $GCP_PROJECT_ID
gcloud scheduler jobs describe gcp3-ai-summary-refresh --project $GCP_PROJECT_ID

# View Cloud Run logs for a specific job
gcloud run services logs read gcp3-backend --limit 100 --project $GCP_PROJECT_ID
```

### Inspect Cache State
```bash
# Export all cache to CSV
/firestore-csv

# Check specific doc
gcloud firestore documents list --collection-id=gcp3_cache --project $GCP_PROJECT_ID | grep "refresh_state"
```

### Validate Backend Changes
```bash
# After any backend deploy, run this skill to verify all 4 rules:
/post-deploy-verify
```

---

## Summary Table: Components in the Refresh Cycle

| Component | Role | Triggering Job | Failure Impact |
|-----------|------|-----------------|-----------------|
| Cloud Scheduler | Trigger refresh jobs | 7 jobs | No refresh starts |
| Backend /refresh/* endpoints | Orchestrate stages | Jobs call these | Data ingestion stops |
| data_client.py | Fetch quotes + analytics | Stages F1-F3, B0 | Industry/market data missing |
| firestore.py | Cache reads/writes | All stages | Stale data returned |
| Gemini API | Content generation | Stages B2-B6 | Blog/articles missing |
| Firestore (gcp3_cache) | Data persistence | All stages | Frontend gets 503 |
| Frontend API routes | Proxy to backend | Page loads | Frontend blank |
| Next.js ISR | Revalidate pages | Page renders | Stale frontend |

---

## Key Takeaways

1. **The refresh cycle is a 3-tier orchestration:**
   - **Tier 1 (Scheduler):** 7 Cloud Scheduler jobs trigger at specific times
   - **Tier 2 (Stages):** Each endpoint runs 3-9 concurrent/sequential stages
   - **Tier 3 (Cache):** All results land in Firestore `gcp3_cache`, then frontend reads

2. **7 endpoints refresh depends on:**
   - ✅ Today is a trading day
   - ✅ Cloud Scheduler jobs trigger (check Cloud Run logs)
   - ✅ Refresh checkpoints exist (`refresh_state:fetch/bake`)
   - ✅ No external API quota exhaustion (Finnhub, Gemini, AV)
   - ✅ Firestore cache writes succeed
   - ✅ Frontend ISR revalidate fires within 60s

3. **To debug "7 endpoints not refreshing":**
   - Run `/debug/status` to see route inventory + cache freshness
   - Check `refresh_state:fetch` checkpoint exists and is today's date
   - Verify Cloud Scheduler jobs ran in the last 2-4 hours
   - Confirm Firestore docs exist and haven't expired
   - Check frontend logs for API proxy errors

