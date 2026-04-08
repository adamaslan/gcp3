# Next.js ISR Optimization Strategy

This document outlines the strategy for implementing **Incremental Static Regeneration (ISR)** across the frontend, taking full advantage of the backend's heavy caching and Cloud Scheduler warmups. 

Because the FastAPI backend uses shared Firestore caches and pre-computes data via automated Cloud Scheduler jobs, the frontend must move away from `force-dynamic` (DDoS-ing the backend on every page view) and instead rely on Next.js background revalidation.

## Core Optimization Steps for ALL Pages
To enable ISR, the following must happen on every Server Component page:
1. **Remove `export const dynamic = "force-dynamic";`** from all `page.tsx` files.
2. **Add Route Segment Config:** Use `export const revalidate = [seconds];` at the top of the file to configure the caching TTL.
3. **Handle Build-Time Data Fetching:** When `force-dynamic` is removed, Next.js will attempt to fetch data during the `npm run build` phase. You must ensure `BACKEND_URL` is set in the build environment (Vercel Build Environment Settings / Cloud Build triggers), or standard ISR pages will fail to compile.
4. **Use Edge Runtimes Extensively:** Re-add `export const runtime = 'edge';` to all `/api/.../route.ts` API proxy files to ensure minimal latency on background revalidations.

---

## 1. Existing Frontend Features (Current Capabilities)

### High-Frequency Data (Live Quotes)
- **Feature:** Industry Quotes (`getQuotes` inside `industry-tracker`)
- **Optimization:** Keep fetching this client-side or use a very low ISR rate.
- **Recommended Revalidate:** `60` (1 minute).

### Mid-Frequency Data (Intraday Changes)
Because the `refresh/intraday` runs at 12:00 PM and 4:15 PM ET, these are safe to cache between 30 and 60 minutes. They won't change faster than the backend updates them.
- **Features:** 
  - Screener (`/screener`)
  - Sector Rotation (`/sector-rotation`)
  - News Sentiment (`/news-sentiment`)
  - Macro Pulse (`/macro-pulse`)
  - Earnings Radar (`/earnings-radar`)
  - Technical Signals (`/technical-signals`)
- **Recommended Revalidate:** `1800` to `3600` (30-60 minutes).

### Low-Frequency Data (Morning/Daily Changes)
Because `refresh/all` runs at 9:35 AM ET, these values are entirely static for the rest of the day.
- **Features:**
  - Morning Brief (`/morning-brief`)
  - AI Summary (`/ai-summary`)
  - Daily Blog (`/daily-blog`)
  - Blog Review (`/blog-review`)
  - Correlation Article (`/correlation-article`)
  - Industry Returns (`/industry-returns`)
  - Market Summary (`/market-summary`)
- **Recommended Revalidate:** `21600` (6 hours) to `86400` (24 hours).

### User-Specific/Dynamic Data
- **Feature:** Portfolio Analyzer (`/portfolio-analyzer`)
- **Optimization:** This feature depends on query parameters (`?tickers=AAPL,MSFT`). It cannot be statically generated via ISR because the inputs are infinite. 
- **Strategy:** Must remain client-side rendered using traditional browser `fetch()` or a library like SWR/React Query. The API proxy route *can* still use Edge runtime.

---

## 2. Unexposed Backend Features (Admin Dashboard Opportunity)

Currently, all the 16 core "financial tools" from the FastAPI backend have corresponding frontend folders and pages. However, the **Backend Admin and Cache Refresh capabilities** have zero frontend exposure.

### Proposed Admin Dashboard (`/admin`)
Creating a protected frontend `/admin` route would provide immense operational value for managing the pipeline without needing `curl` or manual Cloud Scheduler triggers.

**Non-existent Frontend Exposures to Implement:**
1. **Precompute Returns Trigger (`POST /admin/compute-returns`)**: 
   - Expose a button to manually force pre-computation if the database is out of sync.
2. **Seed ETF History (`POST /admin/seed-etf-history`)**:
   - Expose a control panel that displays the count of currently seeded ETFs and a button to delta-update history from `yfinance`.
3. **Manual Cache Warmup (`POST /refresh/all` & `POST /refresh/intraday`)**:
   - Create a dashboard summarizing the cache status.
   - Allow manually triggering the 9:35 AM warmup or the 12:00 PM intraday warmup with a simple click (bypassing the Cloud Scheduler logic for testing/recovery).
   - *Requires*: Passing the `x_scheduler_token` via the Next.js API proxy to securely authorize the calls.

### Conclusion
By adopting `revalidate` and abandoning `force-dynamic`, the frontend will serve immediate responses (from the Vercel/Next.js edge cache) that are effortlessly updated in the background. Coupled with the suggested Admin Dashboard, the operations and performance of the Industry Tracker will be fully optimized.
