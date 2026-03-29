# Persistent Firestore Storage: Efficiency Guide

## gcp3 Project — ETF History Architecture

### The Core Idea

Instead of treating Firestore as a **cache** (temporary, TTL-expires, must re-fetch), treat it as a **permanent data lake** (append-only, compute locally). Fetch full history once via yfinance, then only add new trading days.

```
BEFORE (cache-only):
  Every request → check cache → expired? → hit Finnhub/AV → wait for rate limit → return
  Cost: Alpha Vantage 25 calls/day hard cap, unreliable at scale

AFTER (persistent store):
  Every request → read etf_history Firestore → compute returns locally → return
  Daily cron → append 1 new day per ETF via yfinance (0 API quota cost)
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
GET /industry-returns or /industry-tracker (returns enrichment)
  │
  ├─ 1. etf_history Firestore collection  [PERMANENT STORE]
  │      load_history(symbol) → compute_returns() locally
  │      Periods: 1d, 3d, 1w, 2w, 3w, 1m, 3m, 6m, ytd, 1y, 2y, 5y, 10y
  │      52-week high/low computed from same dataset
  │      0 API calls after initial seed
  │
  └─ 2. Alpha Vantage ANALYTICS_FIXED_WINDOW  [ENRICHMENT ONLY — never blocks]
         5 symbols per call (free tier max)
         Soft daily limit: 20 calls (hard cap: 25)
         50 ETFs → 10 AV calls (batched 5 at a time)
         Only runs when remaining_calls >= calls_needed
         Returns: cumulative_return, mean, stddev for 1-month window only
         NOT used for daily OHLCV history — aggregated stats only
```

---

## API Limits Reference

### Finnhub
| Parameter | Value |
|-----------|-------|
| Free tier rate limit | 60 calls/minute |
| Project rate target | ~20 req/s (semaphore 25 + 50ms stagger) |
| 429 handling | 2s sleep, 1 retry |
| Auth | `X-Finnhub-Token` header |
| Candle history depth | 1 year max on free tier (`/stock/candle`) |
| Used for | Real-time quotes (primary), candle fallback in seed script |

### Alpha Vantage
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
| Parameter | Value |
|-----------|-------|
| API key required | None |
| Practical rate limit | ~100–200 req/min (IP-based, undocumented) |
| Project target | ~40–80 req/min (semaphore 4 + 0.5–1.5s delay) |
| Burst risk | Rapid bursts hit 429 faster than sustained load |
| Seed period | `period="max"` for full ETF inception history |
| Delta period | `period="3mo"` for daily updates |
| Seed script delay | 3s between tickers + exponential backoff (base 12s, doubles, 4 retries max) |
| Bot detection mitigation | Browser User-Agent via `data_client._yf_session()` |
| Multi-symbol | `yf.download(symbols, period="2d")` — 1 network call for N symbols |

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

### `industry_cache` — Computed returns (written by `industry.py`)

Written by `_attach_stored_returns()` on every `/industry-tracker` request. Read by `industry_returns.py` with no API calls.

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

## Seeding: `seed_and_report.py`

Primary seeding tool. Run once to populate `etf_history`, then daily for deltas.

### Source priority

1. **yfinance `period="max"`** — full ETF inception history (no API key, no quota)
2. **Finnhub `/stock/candle`** — 1-year fallback only when yfinance returns empty

Alpha Vantage is **not used** here — its endpoint returns aggregated stats, not OHLCV rows.

### Run

```bash
source /opt/homebrew/Caskroom/miniforge/base/etc/profile.d/conda.sh && \
source /opt/homebrew/Caskroom/miniforge/base/etc/profile.d/mamba.sh && \
mamba activate fin-ai1 && \
GCP_PROJECT_ID=your-project-id python backend/seed_and_report.py
```

`FINNHUB_API_KEY` is optional (only used if yfinance fails for a symbol).

### Output (CSV to stdout, logs to stderr)

```
symbol,action,source,rows_stored,first_date,last_date,total_days,status
IGV,full_seed,yfinance,5040,2006-01-03,2026-03-28,5040,ok
SOXX,full_seed,yfinance,4980,2006-02-08,2026-03-28,4980,ok
```

**Time to seed all 50 ETFs:** ~2.5 minutes (3s between tickers, no quota wait needed).

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
| Daily delta (50 ETFs) | 0 AV, 0 Finnhub | < 3 min | ~95% |
| **Initial seed (one-time)** | **0 AV, 0 Finnhub** | **~2.5 min** | one-time |

---

## Relevant Files

| File | Role |
|------|------|
| `backend/etf_store.py` | Permanent ETF history: `store_history`, `append_daily`, `load_history`, `compute_returns` |
| `backend/seed_and_report.py` | CLI seed + delta script, CSV report output |
| `backend/data_client.py` | Shared clients: Finnhub, yfinance, Alpha Vantage, Firestore cache; all rate-limit logic lives here |
| `backend/industry.py` | 50-industry tracker; `_attach_stored_returns` writes `industry_cache` |
| `backend/industry_returns.py` | Reads `industry_cache`, computes ranked leaders/laggards per period |
| `backend/firestore.py` | Firestore client singleton (`db()`) |

---

**Document Version:** 2.1
**Last Updated:** 2026-03-29
**Project:** gcp3 · Cloud Run + Firestore · us-central1
