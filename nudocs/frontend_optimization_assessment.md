# Frontend Optimization Assessment

This document assesses how well the Next.js frontend is optimized for each of the backend features based on the performance priorities defined in the project's `GEMINI.md` rules.

## Core Optimization Mandates (from GEMINI.md)
1. **ISR**: Prefer `revalidate` over `force-dynamic` in Next.js pages.
2. **Edge**: Use Edge runtime for API proxy routes where possible.
3. **Async**: Use `Promise.all()` for parallel frontend fetches.

---

## 🛑 Critical System-Wide Optimization Failures

### 1. Incremental Static Regeneration (ISR) is entirely disabled
**Rule Violated:** "Prefer `revalidate` over `force-dynamic`"  
**Assessment:** The frontend attempts to implement caching by passing `{ next: { revalidate: X } }` to its fetch calls inside `getData()` functions. However, **every single page** (e.g., `morning-brief/page.tsx`, `screener/page.tsx`, `industry-tracker/page.tsx`, etc.) explicitly declares `export const dynamic = "force-dynamic";` at the top of the file.

In the Next.js App Router, `force-dynamic` completely overrides any localized `revalidate` settings, forcing expensive Server-Side Rendering (SSR) on every single user request. This defeats the backend's elaborate caching mechanisms and significantly slows down page loads.

### 2. Edge Runtime is missing on most APIs
**Rule Violated:** "Use Edge runtime for API proxy routes where possible."  
**Assessment:** The vast majority of API route proxies default to the slower Node.js Serverless runtime instead of the Edge network. 

---

## Feature-by-Feature Breakdown

### 1. Industry Tracker (`/industry-tracker`, `/industry-quotes`, `/industry-returns`)
- **ISR**: ❌ Fails. Uses `force-dynamic` in `page.tsx`.
- **Edge Runtime**: ✅ Optimized. The API routes for `industry-tracker`, `industry-quotes`, and `industry-returns` successfully implement `export const runtime = "edge";`.
- **Async Fetching**: ✅ Optimized. `industry-tracker/page.tsx` properly utilizes `Promise.all([getQuotes(), getReturns()])` to execute parallel fetches, significantly reducing waterfall loading delays.

### 2. Market Data & Screeners (Morning Brief, Screener, Earnings Radar, Macro Pulse, News Sentiment)
- **ISR**: ❌ Fails. All corresponding pages implement `force-dynamic`.
- **Edge Runtime**: ❌ Fails. Their respective `route.ts` API proxy files (like `api/morning-brief/route.ts`) omit the Edge runtime declaration.
- **Async Fetching**: N/A (They typically only make one fetch, so parallelization isn't necessary).

### 3. AI Features (AI Summary, Daily Blog, Blog Review, Correlation Article)
- **ISR**: ❌ Fails. Uses `force-dynamic`.
- **Edge Runtime**: ❌ Fails. None of the AI-driven API routes utilize the Edge runtime. This is particularly harmful here because generating AI text can occasionally suffer from cold starts or timeout configurations inherent to heavier Node serverless instances.

### 4. Interactive Components (Portfolio Analyzer)
- **Client-Side Optimization**: The analyzer correctly uses traditional client-side fetching within React `useState` / standard `fetch()` callbacks (`IndustryTrackerClient.tsx` also does this). 
- **Recommendation**: Could be further modernized with React Query or SWR for automatic deduplication, retries, and optimistic UI updates, though the current raw `fetch` implementation works as intended.

---

## Remediation Plan

To bring the frontend back into compliance with the project's performance mandates, the following actions must be taken:

1. **Remove `force-dynamic`**: Delete `export const dynamic = "force-dynamic";` from all `page.tsx` files. Let Next.js natively rely on the heavily customized `{ next: { revalidate: timeout } }` intervals defined within each `fetch` call.
2. **Inject Edge Configs**: Add `export const runtime = "edge";` to the top of all `src/app/api/.../route.ts` handlers unless they inherently require a specific Node.js API (which, as simple proxies, they do not).
