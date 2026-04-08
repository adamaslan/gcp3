# GCP3 Industry Tracker: Backend & Frontend Architecture Overview

This document provides a breakdown of what the backend does and how the Next.js frontend interacts with it.

## What the Backend Does

The backend is a **FastAPI-based financial data aggregation and analysis engine**. It exposes a suite of "12 MCP Tools," acting as the hub that queries external providers (Finnhub, Alpha Vantage, yfinance, Gemini AI) and caches the results in a shared Firestore database to avoid rate limits and minimize external API costs.

Here are its primary capabilities grouped by function:

### 1. Market Data & Screeners
- **`/morning-brief`**: Aggregates early morning market data.
- **`/industry-tracker` & `/industry-quotes`**: Tracks live data across 50 industries. Has a `compact` mode to return lightweight quotes (just price and change percentage).
- **`/screener`**: Provides stock screener data.
- **`/earnings-radar`**: Tracks upcoming earnings reports.
- **`/macro-pulse`**: Monitors macroeconomic indicators.
- **`/news-sentiment`**: Analyzes the sentiment of recent financial news.
- **`/portfolio-analyzer`**: Takes a comma-separated list of `tickers` to analyze specific portfolios.

### 2. Analytics & Precomputed Signals (Firestore-driven)
- **`/sector-rotation`**: Analyzes sector movement, optionally using Gemini for rule-based analysis.
- **`/technical-signals`**: Fetches technical analysis signals for specific symbols.
- **`/industry-returns`**: Serves precomputed multi-period industry returns (zero external API calls; reads directly from the `industry_cache` in Firestore).
- **`/market-summary`**: Returns historical market summaries over a chosen number of days.

### 3. AI-Generated Syntheses (Powered by Gemini)
- **`/ai-summary`**: Generates an overarching AI market summary.
- **`/daily-blog` & `/blog-review`**: Synthesizes market data into a written daily blog post format and provides a critique/review.
- **`/correlation-article`**: Writes an article about asset correlations.

### 4. Admin & Automated Cache Refreshers (Cloud Scheduler)
- **`/refresh/all`**: A massive multistage pipeline (run at 9:35 AM ET) that warms up the entire cache concurrently. It seeds Firestore and calls all external APIs so the frontend experiences zero latency.
- **`/refresh/intraday`**: A lighter refresh run at noon and end-of-day.
- **`/admin/seed-etf-history` & `/admin/compute-returns`**: Prepopulates historical ETF data using `yfinance` and computes multi-period returns for caching.

---

## Potential Frontend Ways to Work with the Backend

The frontend is a **Next.js (App Router)** application. It leverages the backend using three primary architectural patterns:

### 1. Next.js API Routes (Proxying)
The frontend defines its own API routes under `src/app/api/...` (e.g., `src/app/api/industry-tracker/route.ts`).
- **Why?** It acts as a secure proxy. This prevents the browser from hitting the FastAPI backend directly, avoiding CORS issues, hiding the backend URL structure, and allowing the Next.js server to inject any necessary secrets (if applicable) before forwarding the request.

### 2. React Server Components (ISR / Server-Side Fetching)
The `page.tsx` files (like `src/app/morning-brief/page.tsx` or `src/app/industry-returns/page.tsx`) perform fetching on the server.
- **How it works:** Next.js pages fetch data during the server rendering phase. Following the project's performance mandates (from your `.claude/rules/gcp.md` or `GEMINI.md`), they heavily utilize **Incremental Static Regeneration (ISR)** using Next.js `revalidate` options rather than `force-dynamic`. This means the frontend serves lightning-fast cached HTML and only re-fetches from the FastAPI backend in the background.

### 3. Client-Side Rendering (Dynamic User Interaction)
Components like `PortfolioAnalyzer.tsx` or `IndustryTrackerClient.tsx` execute in the browser.
- **How it works:** When a user interacts with the app (e.g., typing specific stock tickers into the Portfolio Analyzer or choosing different table views), the client component uses `fetch()` to call the Next.js API proxy (`/api/portfolio-analyzer?tickers=AAPL,MSFT`). The Next.js proxy forwards this to the FastAPI backend, retrieves the dynamic data, and updates the UI state. `Promise.all()` is commonly used to fire off multiple requests in parallel to speed up load times.
