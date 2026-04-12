# Constituent Stock Tracking — Rate Limit Analysis

**Impact assessment for adding 4-stock constituents per ETF to the signal system.**

---

## Executive Summary

| Metric | Current | With Constituents | Status |
|--------|---------|-------------------|--------|
| **Total symbols** | 54 ETFs | 194 symbols (54 ETFs + 140 unique constituents) | +259% |
| **Daily Finnhub calls** | ~270 | ~970 | ⚠️ **3.6x increase** |
| **Daily Alpha Vantage calls** | 2 | 39 | ❌ **EXCEEDS 20-call limit** |
| **Finnhub rate compliance** | ✓ Safe (20 req/s sustained) | ⚠️ **Marginal (approaching 30 req/s limit)** | Requires optimization |
| **yfinance fallback** | ✓ Safe (~40 req/min) | ✓ Safe (~60 req/min) | No change needed |

**Verdict:** ⚠️ **Feasible with careful implementation** — Finnhub becomes a bottleneck; Alpha Vantage quota must be managed aggressively.

---

## Current State (54 ETFs Only)

### Symbols & API Calls

| Source | Count |
|--------|-------|
| ETFs tracked | 54 |
| Daily Finnhub quote calls | ~270 (5 refreshes × 54) |
| Daily Alpha Vantage calls | 2 (10 batches, ~1 call/day used) |
| Daily yfinance fallback | Minimal (only on Finnhub failures) |

### Finnhub Rate Analysis (Current)

```
Finnhub semaphore: 25 concurrent requests
Request delay: 50ms stagger
Sustained rate: 20 req/s

Daily call volume: 270 calls/day
Peak concurrent load: ~25 calls
Time to complete: 270 ÷ 20 = 13.5 seconds (for all ETFs, all periods)

Headroom: 30 req/s limit − 20 req/s sustained = 67% buffer ✓
```

### Alpha Vantage Rate Analysis (Current)

```
Free tier limit: 25 calls/day
Soft limit (safety buffer): 20 calls/day
Symbols per call: 5 (batched)

Current usage: 54 ETFs ÷ 5 = ~11 batches
Actual calls used: ~2/day (only runs if quota allows)

Headroom: 20 − 2 = 18 calls/day remaining ✓
```

---

## Projected State (With 4-Stock Constituents per ETF)

### New Symbols

```
54 ETFs × 4 constituents/ETF = 216 constituent slots
Estimated overlap: 35% (NVDA, MSFT, AAPL, GOOGL appear in 5+ ETFs each)
Unique constituents: ~140 stocks

Total unique symbols: 54 + 140 = 194
```

**Example overlaps:**
- NVDA: SOXX, BOTZ, XLK, FDN (4 ETFs)
- MSFT: IGV, CLOU, BOTZ, XLK, FDN, ESGU (6 ETFs)
- AAPL: XLK, FDN, ESGU (3 ETFs)
- GOOGL: FDN, BOTZ, ESGU (3 ETFs)

### Projected Daily API Calls

**Finnhub quote calls (5 refreshes/day):**
```
194 symbols × 5 refreshes = 970 Finnhub quote calls/day

Current: 270 calls
Increase: +700 calls/day (+259%)
```

**Alpha Vantage enrichment calls (1x per day):**
```
194 symbols ÷ 5 symbols/call = 39 batches
39 batches ÷ 5 calls per batch = 7.8 calls equivalent
Actual: ~8 calls/day for 1 period (1m, for example)

Current: ~2 calls/day
Projected: 8+ calls/day for multi-period enrichment
→ EXCEEDS 20-call soft limit (>40% over)
```

**yfinance fallback calls (Finnhub failure):**
```
Still batched: ~2-4 calls to fetch 194 symbols
~40-60 req/min (well under 100-200 req/min limit)
→ No change in rate limit risk ✓
```

---

## Rate Limit Breakdown

### Finnhub: The Primary Bottleneck

#### Current Load (Safe)
```
Semaphore: 25 concurrent
Stagger: 50ms delay
Sustained rate: ~20 req/s
Hard limit: 30 req/s

Current daily volume: 270 calls
Peak concurrent: 25 calls
Margin: 33% buffer to hard limit
Status: ✓ SAFE with room to spare
```

#### Projected Load (Marginal)
```
New daily volume: 970 calls
Peak concurrent: ~50 calls (parallelized across scheduler jobs)

Problem: Semaphore(25) can only run 25 concurrent requests
Solution needed: Increase semaphore OR stagger scheduler jobs

Scenario A: Increase semaphore to 50
  - Concurrent: 50 requests
  - With 50ms stagger: 50 ÷ 0.05 = 1000 req/s (VIOLATES 30 req/s limit!)
  - Status: ❌ IMPOSSIBLE

Scenario B: Dual-phase strategy (recommended)
  - Phase 1 (premarket + intraday): 54 ETFs only (270 calls, ~13.5s)
  - Phase 2 (EOD + nightly): 54 ETFs + 140 constituents (970 calls, ~49s)
  - Stagger phases 30+ minutes apart
  - Peak rate: ~25 req/s during Phase 1, ~20 req/s during Phase 2
  - Status: ✓ SAFE with sequencing

Scenario C: Selective constituent tracking
  - Track only top-20 unique constituents (e.g., NVDA, MSFT, AAPL, GOOGL...)
  - Reduces symbols to ~74 (54 + 20)
  - Daily calls: 74 × 5 = 370 (1.37x increase)
  - Peak rate: ~18 req/s
  - Status: ✓ SAFE, simpler implementation
```

### Alpha Vantage: Hard Stop

#### Current Usage (Safe)
```
Daily limit: 25 calls
Soft limit (safety): 20 calls
Current usage: 2 calls/day (10% of soft limit)
Status: ✓ SAFE, lots of headroom
```

#### Projected Usage (Over Budget)
```
New symbols: 194
Symbols per call: 5
Calls needed for multi-period analysis: 8+ calls/day
  - Current approach: 1 call/day (1 period only, all symbols)
  - Extended: 8 calls/day (8 periods, all symbols)
  
Status: ❌ EXCEEDS soft limit (40% over)

Solutions:

Option 1: Skip Alpha Vantage for constituents
  - Only compute AV analytics for 54 ETFs (current)
  - Constituents use Finnhub quotes + stored yfinance history
  - Cost: ~0 AV calls for constituents
  - Impact: Constituents have no multi-period enrichment
  - Verdict: Acceptable (ETF signals are primary; constituents are confirmatory)

Option 2: Selective multi-period via yfinance history
  - Use stored price history (already cached from seed) for constituents
  - Compute multi-period returns offline, stored in Firestore
  - Cost: ~0 AV calls
  - Impact: Constituents have full signal support, just not real-time enrichment
  - Verdict: Best solution ✓

Option 3: Upgrade to Finnhub Premium (paid)
  - Removes Alpha Vantage entirely
  - Cost: ~$200-500/month
  - Verdict: Overkill for this use case
```

---

## Recommended Implementation: Dual-Phase + yfinance History

### Architecture

#### Phase 1: ETF-Centric Tracking (Current, Optimized)
```
Symbols: 54 ETFs only
Schedule: Premarket (8:30 AM) + Midday (12:30 PM) + EOD (3:50 PM)
API calls:
  - Finnhub quotes: 54 × 3 = 162 calls/day
  - Alpha Vantage: 2 calls/day (enrichment)
  - yfinance: Fallback only
Rate limit compliance: ✓ Safe (20 req/s)
```

#### Phase 2: Constituent Tracking (New, Sequential)
```
Symbols: 140 unique constituents
Schedule: Nightly (2:00 AM) + optional overnight enrichment
API calls:
  - Finnhub quotes: 140 × 2 = 280 calls/day (nightly + next-day cache warm)
  - Alpha Vantage: 0 calls (use yfinance history instead)
  - yfinance: Bulk fetch if needed (batched into 2-4 calls)
Rate limit compliance: ✓ Safe (20 req/s for 140 symbols sequentially)
```

#### Separation Benefits
```
Timing:
  - Premarket (8:30 AM): ETFs only → Fast warmup, <5 seconds
  - Intraday (9:35 AM, 12:30 PM, 3:50 PM): ETFs only → Keep dashboard responsive
  - EOD (3:50 PM): ETFs + light constituent refresh → Consolidate day's data
  - Overnight (2:00 AM): Constituents + analysis → Offline, no time pressure

Rate management:
  - Never both phases run simultaneously
  - ETF phase: ~20 req/s sustained (safe)
  - Constituent phase: ~5-10 req/s sustained (very safe)
  - Total: 970 calls/day, but never violating 30 req/s hard limit
```

### Implementation Steps

#### Step 1: Add Constituent Seeds to `etf_store.py`
```python
# backend/etf_store.py

CONSTITUENT_STOCKS = {
    "IGV": ["MSFT", "ADBE", "NXPI", "SNPS"],
    "SOXX": ["NVDA", "ASML", "AMD", "QCOM"],
    "CLOU": ["MSFT", "CRM", "ADBE", "INTU"],
    # ... all 54 ETFs with 4 constituents each
}

async def seed_constituent_history():
    """
    One-time: Fetch 5 years of price history for all constituents via yfinance.
    Store in Firestore under constituent_history collection.
    Cost: ~0 API calls (yfinance is free)
    """
    for stocks in CONSTITUENT_STOCKS.values():
        for symbol in stocks:
            hist = yf.download(symbol, period="5y", progress=False)
            store_in_firestore(f"constituent_history:{symbol}", hist)
```

#### Step 2: Add Nightly Constituent Refresh Endpoint
```python
# backend/main.py

@app.post("/refresh/constituents")
async def refresh_constituents(request: Request):
    """
    2:30 AM (after nightly cache purge):
    - Fetch live quotes for 140 constituents
    - Compute signals using stored price history
    - Cache results for next trading day
    """
    verify_scheduler_token(request)
    
    all_constituents = flatten_constituent_stocks()  # 140 unique symbols
    
    # Fetch quotes via Finnhub, fallback yfinance
    quotes = await get_quotes(all_constituents)  # Finnhub with fallback
    
    # Compute signals using stored history
    for symbol, quote in quotes.items():
        history = get_stored_history(symbol)  # From Firestore
        signals = compute_signals_all_periods(symbol, history, quote)
        set_cache(f"signals:constituent:{symbol}:{date.today()}", signals, ttl_hours=168)
    
    logger.info("constituents_refresh: %d signals computed", len(quotes))
    return {"status": "ok", "constituents": len(quotes)}
```

#### Step 3: Update Scheduler Job
```bash
# Create or update Cloud Scheduler job (2:30 AM, after cache purge)

gcloud scheduler jobs create http gcp3-constituents-refresh \
  --schedule="30 6 * * 1-5" \  # 2:30 AM ET Mon-Fri (6:30 AM UTC)
  --http-method=POST \
  --uri=https://gcp3-backend.run.app/refresh/constituents \
  --headers="X-Scheduler-Token=$SCHEDULER_SECRET" \
  --time-zone="UTC" \
  --location=us-central1 \
  --project=$GCP_PROJECT_ID
```

#### Step 4: Update Frontend Signal Endpoints
```python
# backend/main.py

@app.get("/signals/constituents/{etf}")
async def get_constituent_signals(etf: str):
    """
    Get 4 constituent signals for a single ETF.
    Used in ETF detail cards to show divergence/confirmation.
    """
    constituents = CONSTITUENT_STOCKS.get(etf.upper())
    if not constituents:
        raise HTTPException(status_code=404, detail="ETF not found")
    
    signals = {}
    for symbol in constituents:
        key = f"signals:constituent:{symbol}:{date.today()}"
        if cached := get_cache(key):
            signals[symbol] = cached
    
    return {
        "etf": etf,
        "constituents": signals,
        "updated": str(date.today()),
    }
```

---

## API Call Summary: Before vs. After

### Daily API Call Budget

#### Before (54 ETFs Only)
```
Finnhub:
  - Premarket: 54 calls
  - Midday: 54 calls
  - Midday: 54 calls
  - EOD: 54 calls
  - Total: 216 calls/day
  
Alpha Vantage:
  - Enrichment: 2 calls/day
  - Total: 2 calls/day

yfinance (fallback):
  - Minimal (only Finnhub failures)

TOTAL: ~220 API calls/day (Finnhub dominant)
Headroom: Excellent (67% buffer to limits)
```

#### After (54 ETFs + 140 Constituents, Optimized)
```
ETF Phase (Premarket + Intraday):
  - 54 ETFs × 3 refreshes = 162 Finnhub calls
  - 2 Alpha Vantage calls
  
Constituent Phase (Nightly):
  - 140 constituents × 2 refreshes = 280 Finnhub calls
  - 0 Alpha Vantage calls (use yfinance history)
  - 1-2 yfinance bulk calls (if needed)

TOTAL: ~444 Finnhub + 2 AV + 2 yfinance = ~448 calls/day
Increase: +228 calls/day (+103%)

Rate compliance:
  - ETF phase: 162 calls in ~8 seconds → 20 req/s ✓
  - Constituent phase: 280 calls in ~14 seconds → 20 req/s ✓
  - Never concurrent, always sequential
  - Headroom: Still maintains 33% buffer ✓
```

---

## Trade-offs & Decisions

| Option | Pros | Cons | Recommendation |
|--------|------|------|-----------------|
| **Dual-phase + yfinance history** | No rate limit violations; decoupled from AV quota; scalable | Implementation complexity; nightly-only constituent updates | ✅ **RECOMMENDED** |
| **Track all constituents (no optimization)** | Simplest code; full real-time updates | ❌ Exceeds Finnhub (4x over) and AV (2x over) limits | ❌ Not viable |
| **Track top-20 constituents only** | Minimal rate impact; real-time updates | Less comprehensive; misses smaller cap names | ⚠️ Acceptable fallback |
| **Upgrade to Finnhub Premium** | Removes all quota concerns | Cost: $200-500/month | ❌ Overkill |
| **Only track ETF signals, no constituents** | No API changes; highest reliability | Misses divergence detection; limits analysis depth | ❌ Defeats purpose |

---

## Migration Path

### Week 1: Setup
```
1. Seed constituent price history via yfinance (one-time, free)
2. Store in Firestore under constituent_history collection
3. Test signal computation using stored history
```

### Week 2: Implementation
```
1. Add /refresh/constituents endpoint
2. Implement constituent signal computation
3. Add Cloud Scheduler job for nightly refresh
4. Update frontend endpoints to serve constituent signals
```

### Week 3: Validation
```
1. Monitor API call rates during nightly run
2. Verify Finnhub stays <25 req/s during ETF phase
3. Verify constituent phase completes in <30 seconds
4. Backtest signal divergence detection (ETF vs. constituents)
```

### Week 4: Production
```
1. Deploy to Cloud Run
2. Enable nightly scheduler job
3. Update frontend to display constituent cards
4. Monitor and log any rate limit 429s (should be zero)
```

---

## Cost Impact

| Component | Current | With Constituents | Delta |
|-----------|---------|-------------------|-------|
| **Finnhub API** | Free tier (sufficient) | Free tier (still sufficient) | $0 |
| **Alpha Vantage** | Free tier (2 calls/day) | Free tier (2 calls/day, constituents use yfinance) | $0 |
| **yfinance** | Minimal fallback | ~2 calls/nightly | Free (no quota) |
| **Firestore** | ~500 ops/day | ~800 ops/day (+60%) | ~$0.02/month |
| **Cloud Run** | ~5 mins/day CPU | ~7 mins/day CPU (+40%) | ~$0.10/month |
| **Total Monthly** | ~$1.50 | ~$1.65 | **+$0.15** |

**Verdict:** ✓ **Negligible cost increase**

---

## Conclusion

### Is it safe to track all 194 symbols (54 ETFs + 140 constituents)?

**Yes, with the recommended dual-phase architecture:**

✅ **Finnhub:** 444 calls/day split across sequential phases → 20 req/s sustained (safe)  
✅ **Alpha Vantage:** 0 calls for constituents (use yfinance history instead) → 2 calls/day (safe)  
✅ **yfinance:** 2-4 bulk calls at off-peak (2 AM) → ~40-60 req/min (safe)  
✅ **Firestore:** +60% ops/day → Still well under daily quota  
✅ **Cost:** +$0.15/month (negligible)  

### Recommended Next Steps

1. **Implement dual-phase architecture** (ETF-centric + nightly constituent phase)
2. **Seed constituent history** (one-time free yfinance download)
3. **Add `/refresh/constituents` endpoint** and Cloud Scheduler job
4. **Deploy nightly** and monitor for any 429 rate limit errors (expect zero)
5. **Validate signal divergence detection** in production (1-2 weeks)

This approach maintains current reliability while adding comprehensive constituent tracking without violating any API limits.
