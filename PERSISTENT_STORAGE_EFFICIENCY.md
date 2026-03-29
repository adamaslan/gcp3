# Persistent Firestore Storage: Efficiency Guide

## gcp3 Project — ETF History Architecture

### The Core Idea

Instead of treating Firestore as a **cache** (temporary, TTL-expires, must re-fetch), treat it as a **permanent data lake** (append-only, compute locally). Fetch full history once, then only add new trading days.

```
BEFORE (cache-only):
  Every request → check cache → expired? → hit Finnhub/AV → wait for rate limit → return
  Cost: Alpha Vantage 25 calls/day hard cap, unreliable at scale

AFTER (persistent store):
  Every request → read etf_history Firestore → compute returns locally → return
  Daily cron → append 1 new day per ETF via Finnhub/yfinance (0 AV quota cost)
  Cost: ~0 API calls after initial seed
```

---

## Data Resolution Chain

### Quote Requests (`data_client.py`)

```
GET /industry-tracker or any quote endpoint
  │
  ├─ 1. Firestore cache (gcp3_cache, TTL-checked on read via expires_at)
  │      50–200ms, 0 API cost, shared across all Cloud Run instances
  │
  ├─ 2. Finnhub /quote  [PRIMARY live source]
  │      semaphore(25) + 50ms stagger → ~20 req/s sustained
  │      429 handling: 2s sleep + single retry
  │      Key sent via X-Finnhub-Token header (never in URL)
  │
  └─ 3. yfinance  [FALLBACK]
         No API key required
         semaphore(4) + 0.5–1.5s randomized delay → ~40–80 req/min
         Runs in ThreadPoolExecutor(max_workers=4) — sync library
         Browser User-Agent set via _yf_session() to reduce bot-detection risk
         Bulk yf.download() used for multi-symbol requests (1 network call)
```

### Returns / Performance Data (`industry.py` → `etf_store.py`)

```
GET /industry-tracker (at end of every request)
  │
  └─ _attach_stored_returns()
       ├─ etf_store.compute_returns(etf) for each unique ETF
       │    └─ load_history() from etf_history Firestore collection
       │       Periods: 1d, 3d, 1w, 2w, 3w, 1m, 3m, 6m, ytd, 1y, 2y, 5y, 10y
       │       52-week high/low from same dataset — 0 API calls
       │
       └─ batch-writes results → industry_cache Firestore collection
            consumed by /industry-returns with no further API calls

GET /industry-returns
  └─ reads industry_cache directly (written by above)
       0 API calls, 0 etf_store reads
```

> **Important:** `seed_and_report.py` only writes `etf_history`. The `industry_cache`
> collection is populated exclusively by `_attach_stored_returns()` on each
> `/industry-tracker` request. Run `/industry-tracker` once after seeding to
> populate `industry_cache` before using `/industry-returns`.

### Alpha Vantage Enrichment (`industry.py`)

```
After quotes are fetched in get_industry_data():
  └─ Only runs if av_remaining_calls() >= calls_needed
       5 symbols per call (free tier max)
       50 ETFs → 10 calls
       Returns: cumulative_return, mean, stddev (1-month window)
       NOT used for OHLCV history — enrichment only, never blocks quotes
```

---

## API Limits Reference

### Finnhub
Docs: [finnhub.io/docs/api](https://finnhub.io/docs/api) · Rate limits: [finnhub.io/docs/api/rate-limit](https://finnhub.io/docs/api/rate-limit)

| Parameter | Value |
|-----------|-------|
| Free tier rate limit | 60 calls/minute |
| Project rate target (quotes) | ~20 req/s (semaphore 25 + 50ms stagger) |
| Project rate target (seed) | ~8 req/s (120ms between requests) |
| 429 handling (quotes) | 2s sleep, 1 retry |
| 429 handling (seed) | 3s sleep, 1 retry |
| Auth | `X-Finnhub-Token` header |
| Candle history depth | 1 year max on free tier (`/stock/candle`) |
| Used for | Real-time quotes (primary); OHLCV seed (primary in `seed_and_report.py`) |

### Alpha Vantage
Docs: [alphavantage.co/documentation](https://www.alphavantage.co/documentation/) · Analytics API: [alphavantageapi.co/timeseries/analytics](https://alphavantageapi.co/timeseries/analytics)

| Parameter | Value |
|-----------|-------|
| Free tier daily cap | 25 calls/day (hard) |
| Project soft limit | 20 calls/day (`_AV_DAILY_LIMIT`) |
| Buffer | 5 calls held in reserve |
| Symbols per call | 5 (`_AV_SYMBOLS_PER_CALL`, free tier max) |
| 50 ETFs cost | 10 calls |
| Endpoint | `ANALYTICS_FIXED_WINDOW` via `alphavantageapi.co/timeseries/analytics` |
| Returns fields | `CUMULATIVE_RETURN`, `MEAN`, `STDDEV` |
| **Not used for** | OHLCV price history — aggregated stats only |
| Key env var | `ALPHA_VANTAGE_KEY` |
| Call counter | In-process `_av_call_count`, resets at midnight UTC |

### yfinance
Docs: [pypi.org/project/yfinance](https://pypi.org/project/yfinance/) · GitHub: [github.com/ranaroussi/yfinance](https://github.com/ranaroussi/yfinance)

| Parameter | Value |
|-----------|-------|
| API key required | None |
| Practical rate limit | ~100–200 req/min (IP-based, undocumented) |
| Project target (quotes) | ~40–80 req/min (semaphore 4 + 0.5–1.5s delay) |
| Burst risk | Rapid bursts hit 429 faster than sustained load |
| Seed script role | FALLBACK only — used when Finnhub returns no data |
| Seed period | `period="max"` for full ETF inception history |
| Delta period | `period="3mo"` for daily updates |
| Seed script delay | 4s between fallback attempts, single attempt per symbol |
| Bot detection (quotes) | Browser User-Agent via `data_client._yf_session()` |
| Bot detection (seed) | Browser User-Agent set inline in `_yf_fetch()` |
| Bot detection (admin seed) | **NOT set** — `industry.py:seed_etf_history()` uses bare `yf.Ticker()` |
| Multi-symbol (quotes) | `yf.download(symbols, period="2d")` — 1 network call for N symbols |

### Firestore
| Resource | Free Tier | gcp3 Usage |
|----------|-----------|------------|
| Document reads | 50,000/day | ~500–1,000/day |
| Document writes | 20,000/day | ~50/day (daily deltas) |
| Storage | 1 GB | ~50 MB (50 ETFs × ~1 MB each) |
| Network egress | 10 GB/month | < 500 MB/month |
| Batch write limit | 500 ops/batch | Project uses 450 (`_FIRESTORE_BATCH_MAX_OPS`) |

**All usage fits comfortably within Firestore free tier.**

---

## Firestore Collections

### `etf_history` — Permanent price store

Written by: `etf_store.store_history()` (full seed) and `etf_store.append_daily()` (deltas).

```
etf_history/
└── {SYMBOL}/                   # e.g. IGV, SOXX, HACK
    ├── symbol, source
    ├── first_date, last_date, total_days
    ├── last_updated (ISO timestamp)
    ├── storage_mode: "embedded" | "chunked"
    │
    ├── [embedded — ≤ 2000 rows]
    │   └── prices: [{date, adjusted_close, volume}, ...]
    │
    └── [chunked — > 2000 rows, used for ETFs with 20+ year history]
        └── years/
            └── {YYYY}: [{date, adjusted_close, volume}, ...]
```

Threshold: `_MAX_EMBEDDED_RECORDS = 2000`. Chunked writes use batches of max 450 ops.

### `industry_cache` — Computed returns

Written by: `industry.py:_attach_stored_returns()` on every `/industry-tracker` request.
Read by: `industry_returns.py` via `/industry-returns` — zero API calls.

**NOT written by `seed_and_report.py`.** Requires at least one `/industry-tracker` call after seeding.

```
industry_cache/
└── {Industry Name}/    # e.g. "Software", "Semiconductors"
    ├── industry, sector, etf
    ├── returns: {1d, 3d, 1w, 2w, 3w, 1m, 3m, 6m, ytd, 1y, 2y, 5y, 10y}
    ├── 52w_high, 52w_low
    └── updated (ISO timestamp)
```

### `gcp3_cache` — Short-term TTL cache

Document key: `{type}:{date}` e.g. `industry50:2026-03-29`. Field `expires_at` checked on every read; expired docs treated as misses. TTL: 24h for industry data, 6h for returns rankings.

---

## 50 ETFs by Sector

| Sector | Industries |
|--------|-----------|
| Technology | Software (IGV), Semiconductors (SOXX), Cloud (CLOU), Cybersecurity (HACK), AI (BOTZ), Internet (FDN), Hardware (XLK), Telecom (VOX) |
| Healthcare | Biotech (IBB), Pharma (XPH), Providers (IHF), Devices (IHI), Managed Care (XLV), REIT (VHT) |
| Financials | Banks (KBE), Insurance (KIE), Asset Mgmt (PFM), Fintech (FINX), REITs (VNQ), Payments (IPAY), Regional Banks (KRE) |
| Consumer | Retail (XRT), E-Commerce (IBUY), Staples (XLP), Discretionary (XLY), Restaurants (BITE), Apparel (PEJ), Auto (CARZ), Luxury (LUXE) |
| Energy & Materials | Oil & Gas (XLE), Renewables (ICLN), Mining (XME), Steel (SLX), Chemicals (XLB) |
| Industrials | Aerospace (ITA), Transport (XTN), Construction (ITB), Logistics (FTXR), Industrials (XLI) |
| Real Estate | Real Estate (IYR), Infrastructure (PAVE), Homebuilders (XHB), Commercial RE (INDS) |
| Communications | Media (PBS), Entertainment (PEJ), Social Media (SOCL) |
| Other | Utilities (XLU), Agriculture (DBA), Cannabis (MSOS), ESG (ESGU) |

---

## Seeding

### Two seed paths — key differences

| | `seed_and_report.py` | `POST /admin/seed-etf-history` |
|---|---|---|
| Source | Finnhub primary → yfinance fallback | yfinance only |
| History depth | 1 year (Finnhub free tier) | `max` on first run, `3mo` on delta |
| Rate limiting | 120ms/req (Finnhub), 4s/req (yfinance fallback) | None |
| User-Agent | Set inline in `_yf_fetch()` | **Not set** — bare `yf.Ticker()` |
| Output | CSV report to stdout | JSON `{etfs, total_rows, detail}` |
| Writes `industry_cache` | No | No |
| When to use | Production seeding | Quick trigger via scheduler |

### `seed_and_report.py` — CLI (recommended)

```bash
source /opt/homebrew/Caskroom/miniforge/base/etc/profile.d/conda.sh && \
source /opt/homebrew/Caskroom/miniforge/base/etc/profile.d/mamba.sh && \
mamba activate fin-ai1 && \
GCP_PROJECT_ID=your-project-id FINNHUB_API_KEY=your-finnhub-api-key \
python backend/seed_and_report.py
```

Omit `FINNHUB_API_KEY` to force yfinance-only mode (slower, full history).

**Time:** ~6s for all 50 ETFs via Finnhub (120ms × 50). yfinance fallback adds ~4s per symbol.

### `POST /admin/seed-etf-history` — HTTP trigger

```
POST /admin/seed-etf-history
X-Scheduler-Token: your-scheduler-token
```

### After seeding — populate `industry_cache`

```bash
curl https://your-cloud-run-url/industry-tracker
```

This triggers `_attach_stored_returns()` which computes all returns from `etf_history` and writes `industry_cache`. Required before `/industry-returns` will return data.

### CSV output (`seed_and_report.py`)

```
symbol,action,source,rows_stored,first_date,last_date,total_days,status
IGV,full_seed,finnhub,365,2025-03-29,2026-03-28,365,ok
SOXX,full_seed,finnhub,365,2025-03-29,2026-03-28,365,ok
CLOU,full_seed,yfinance,4200,2014-01-01,2026-03-28,4200,ok
```

---

## API Cost Comparison

### Before (cache-only)

| Operation | AV Calls | Time | Reliability |
|-----------|----------|------|-------------|
| Single industry refresh | 1 | ~12s | ~80% |
| All 50 industries | 50 | 2 days | ~60% |
| Morning brief | 10–50 | 10+ min | ~60% |
| **Daily cap** | **25 hard** | — | unreliable |

### After (persistent store)

| Operation | API Calls | Time | Reliability |
|-----------|-----------|------|-------------|
| Single ETF returns lookup | 0 | < 200ms | 100% |
| All 50 industries returns | 0 | < 2s | 100% |
| Morning brief | 0 | < 5s | 100% |
| Daily delta (50 ETFs, Finnhub) | 0 AV | ~6s | ~95% |
| **Initial seed (one-time)** | **0 AV** | **~6s** | one-time |

---

## Relevant Files

| File | Role |
|------|------|
| `backend/etf_store.py` | Permanent ETF history: `store_history`, `append_daily`, `load_history`, `compute_returns` |
| `backend/seed_and_report.py` | CLI seed + delta script, Finnhub primary / yfinance fallback, CSV report |
| `backend/data_client.py` | Shared clients: Finnhub, yfinance, Alpha Vantage, Firestore cache; all rate-limit logic |
| `backend/industry.py` | 50-industry tracker; `_attach_stored_returns` writes `industry_cache`; `seed_etf_history` for HTTP trigger |
| `backend/industry_returns.py` | Reads `industry_cache`, ranks leaders/laggards per period, 0 API calls |
| `backend/firestore.py` | Firestore client singleton (`db()`) |

---

**Document Version:** 2.2
**Last Updated:** 2026-03-29
**Project:** gcp3 · Cloud Run + Firestore · us-central1
