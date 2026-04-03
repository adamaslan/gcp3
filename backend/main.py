"""GCP3 Finance API - 12 MCP tools (9 Finnhub + 3 shared Firestore)."""
import asyncio
import logging
import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from industry import compute_returns, get_industry_data, get_industry_quotes, seed_etf_history
from morning import get_morning_brief
from screener import get_screener_data
from sector_rotation import get_sector_rotation  # force_rule_based param added
from earnings_radar import get_earnings_radar
from macro_pulse import get_macro_pulse
from news_sentiment import get_news_sentiment
from portfolio_analyzer import get_portfolio_analysis
from ai_summary import get_ai_summary, refresh_ai_summary
from technical_signals import get_technical_signals
from industry_returns import get_industry_returns
from market_summary import get_market_summary
from daily_blog import get_daily_blog, refresh_daily_blog
from blog_reviewer import get_blog_review, refresh_blog_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="GCP3 Finance API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "2.1.0", "tools": 12}


# ── Tool 1: Morning Brief ─────────────────────────────────────────────────────
@app.get("/morning-brief")
async def morning_brief(request: Request) -> dict:
    logger.info("GET /morning-brief from %s", request.client)
    try:
        data = await get_morning_brief()
        logger.info("GET /morning-brief success")
        return data
    except Exception as exc:
        logger.exception("GET /morning-brief failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Tool 2: Industry Tracker ─────────────────────────────────────────────────
@app.get("/industry-tracker")
async def industry_tracker(request: Request) -> dict:
    logger.info("GET /industry-tracker from %s", request.client)
    try:
        data = await get_industry_data()
        logger.info("GET /industry-tracker success")
        return data
    except Exception as exc:
        logger.exception("GET /industry-tracker failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Industry Quotes (live prices only, short cache) ──────────────────────────
@app.get("/industry-quotes")
async def industry_quotes(
    request: Request,
    view: str = Query(default="full", description="'compact' returns only sector/etf/price/change_pct"),
) -> dict:
    logger.info("GET /industry-quotes view=%s from %s", view, request.client)
    try:
        data = await get_industry_quotes()
        if view == "compact":
            data = _compact_quotes(data)
        logger.info("GET /industry-quotes success")
        return data
    except Exception as exc:
        logger.exception("GET /industry-quotes failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


def _compact_quotes(data: dict) -> dict:
    """Strip full quote payload to essential fields only (~70% smaller)."""
    compact_industries = {
        name: {
            "sector": v.get("sector"),
            "etf": v.get("etf"),
            "price": v.get("price"),
            "change_pct": v.get("change_pct"),
        }
        for name, v in data.get("industries", {}).items()
    }
    compact_row = lambda r: {
        "industry": r["industry"],
        "sector": r.get("sector"),
        "etf": r.get("etf"),
        "change_pct": r.get("change_pct"),
    }
    return {
        "date": data.get("date"),
        "total": data.get("total"),
        "industries": compact_industries,
        "leaders": [compact_row(r) for r in data.get("leaders", [])],
        "laggards": [compact_row(r) for r in data.get("laggards", [])],
    }


# ── Admin: Precompute returns from etf_store → industry_cache ────────────────
@app.post("/admin/compute-returns")
async def compute_returns_endpoint(
    request: Request,
    x_scheduler_token: Optional[str] = Header(default=None),
) -> dict:
    """Precompute multi-period returns from stored ETF history into industry_cache.

    Zero Finnhub or Alpha Vantage calls. Safe to run hourly or daily via
    Cloud Scheduler. Must run after seed-etf-history has populated etf_store.
    """
    _verify_scheduler(x_scheduler_token)
    logger.info("POST /admin/compute-returns triggered")
    try:
        result = await compute_returns()
        return result
    except Exception as exc:
        logger.exception("POST /admin/compute-returns failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


# ── Tool 3: Stock Screener ────────────────────────────────────────────────────
@app.get("/screener")
async def screener(request: Request) -> dict:
    logger.info("GET /screener from %s", request.client)
    try:
        data = await get_screener_data()
        logger.info("GET /screener success")
        return data
    except Exception as exc:
        logger.exception("GET /screener failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Tool 4: Sector Rotation ───────────────────────────────────────────────────
@app.get("/sector-rotation")
async def sector_rotation(request: Request) -> dict:
    logger.info("GET /sector-rotation from %s", request.client)
    try:
        data = await get_sector_rotation()
        logger.info("GET /sector-rotation success")
        return data
    except Exception as exc:
        logger.exception("GET /sector-rotation failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Tool 5: Earnings Radar ────────────────────────────────────────────────────
@app.get("/earnings-radar")
async def earnings_radar(request: Request) -> dict:
    logger.info("GET /earnings-radar from %s", request.client)
    try:
        data = await get_earnings_radar()
        logger.info("GET /earnings-radar success")
        return data
    except Exception as exc:
        logger.exception("GET /earnings-radar failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Tool 6: Macro Pulse ───────────────────────────────────────────────────────
@app.get("/macro-pulse")
async def macro_pulse(request: Request) -> dict:
    logger.info("GET /macro-pulse from %s", request.client)
    try:
        data = await get_macro_pulse()
        logger.info("GET /macro-pulse success")
        return data
    except Exception as exc:
        logger.exception("GET /macro-pulse failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Tool 7: News Sentiment ────────────────────────────────────────────────────
@app.get("/news-sentiment")
async def news_sentiment(request: Request) -> dict:
    logger.info("GET /news-sentiment from %s", request.client)
    try:
        data = await get_news_sentiment()
        logger.info("GET /news-sentiment success")
        return data
    except Exception as exc:
        logger.exception("GET /news-sentiment failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Tool 8: Portfolio Analyzer ────────────────────────────────────────────────
@app.get("/portfolio-analyzer")
async def portfolio_analyzer(
    request: Request,
    tickers: Optional[str] = Query(default=None, description="Comma-separated tickers, e.g. AAPL,MSFT,TSLA"),
) -> dict:
    logger.info("GET /portfolio-analyzer from %s tickers=%s", request.client, tickers)
    try:
        ticker_list = [t.strip() for t in tickers.split(",")] if tickers else None
        data = await get_portfolio_analysis(ticker_list)
        logger.info("GET /portfolio-analyzer success")
        return data
    except Exception as exc:
        logger.exception("GET /portfolio-analyzer failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Tool 9: AI Market Summary ─────────────────────────────────────────────────
@app.get("/ai-summary")
async def ai_summary(request: Request) -> dict:
    logger.info("GET /ai-summary from %s", request.client)
    try:
        data = await get_ai_summary()
        logger.info("GET /ai-summary success")
        return data
    except Exception as exc:
        logger.exception("GET /ai-summary failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Tool 10: Daily Blog ───────────────────────────────────────────────────────
@app.get("/daily-blog")
async def daily_blog(request: Request) -> dict:
    logger.info("GET /daily-blog from %s", request.client)
    try:
        return await get_daily_blog()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ── Tool 11: Blog Review ──────────────────────────────────────────────────────
@app.get("/blog-review")
async def blog_review(request: Request) -> dict:
    logger.info("GET /blog-review from %s", request.client)
    try:
        return await get_blog_review()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ── Scheduler auth helper ─────────────────────────────────────────────────────
def _verify_scheduler(token: Optional[str]) -> None:
    """Raise 401 if token does not match SCHEDULER_SECRET env var."""
    expected = os.environ.get("SCHEDULER_SECRET")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _warm_backend2(client: httpx.AsyncClient, path: str) -> dict:
    """Call a backend2 endpoint for cache warming. Swallows failures gracefully."""
    backend2_url = os.environ.get("BACKEND2_URL", "").rstrip("/")
    if not backend2_url:
        logger.warning("refresh: BACKEND2_URL not set — skipping %s", path)
        return {"status": "skipped", "reason": "BACKEND2_URL not configured"}
    try:
        r = await client.get(f"{backend2_url}{path}", timeout=30)
        r.raise_for_status()
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("refresh: backend2 %s failed: %s", path, exc)
        return {"status": "error", "detail": str(exc)}


# ── POST /refresh/all — Morning full warm-up (Cloud Scheduler, 9:35 AM ET) ───
@app.post("/refresh/all")
async def refresh_all(
    request: Request,
    x_scheduler_token: Optional[str] = Header(default=None),
) -> dict:
    """Full cache warm-up in dependency order. Called by Cloud Scheduler at 9:35 AM ET Mon-Fri.

    Stages:
        0  Firestore readers — validate pipeline data is present (zero API cost)
        1  Independent market data — concurrent Finnhub calls
        2  Sector + screener — concurrent (Finnhub + Gemini)
        3  Industry — isolated to stay under Alpha Vantage 25-call/day limit
        4  Backend2 fan-out — scan + key Fibonacci levels via yfinance (no Finnhub quota)
        5  AI synthesis — must run last; aggregates all prior warm caches
    """
    _verify_scheduler(x_scheduler_token)
    logger.info("POST /refresh/all started")
    stages: dict[str, dict] = {}
    overall_start = time.perf_counter()

    # Stage 0 — Firestore readers
    t0 = time.perf_counter()
    try:
        await asyncio.gather(
            get_technical_signals(),
            get_market_summary(),
            get_industry_returns(),
        )
        stages["firestore_readers"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        logger.warning("refresh/all stage 0 error: %s", exc)
        stages["firestore_readers"] = {"status": "error", "detail": str(exc)}

    # Stage 1 — Independent market data (concurrent)
    t0 = time.perf_counter()
    try:
        await asyncio.gather(
            get_morning_brief(),
            get_macro_pulse(),
            get_earnings_radar(),
            get_news_sentiment(),
        )
        stages["market_data"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        logger.warning("refresh/all stage 1 error: %s", exc)
        stages["market_data"] = {"status": "error", "detail": str(exc)}

    # Stage 2 — Sector rotation + screener (concurrent)
    t0 = time.perf_counter()
    try:
        await asyncio.gather(
            get_sector_rotation(),
            get_screener_data(),
        )
        stages["sector_screener"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        logger.warning("refresh/all stage 2 error: %s", exc)
        stages["sector_screener"] = {"status": "error", "detail": str(exc)}

    # Stage 3 — Industry (isolated: 50 Finnhub + 10 Alpha Vantage batches)
    t0 = time.perf_counter()
    try:
        await get_industry_data(enrich_av=True)
        stages["industry"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        logger.warning("refresh/all stage 3 error: %s", exc)
        stages["industry"] = {"status": "error", "detail": str(exc)}

    # Stage 4 — Backend2 HTTP fan-out (yfinance, no Finnhub quota consumed)
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=35) as b2_client:
        fib_symbols = ["SPY", "QQQ", "NVDA", "AAPL", "GLD"]
        b2_results = await asyncio.gather(
            _warm_backend2(b2_client, "/scan"),
            *[_warm_backend2(b2_client, f"/fibonacci/{sym}") for sym in fib_symbols],
        )
    b2_statuses = [r["status"] for r in b2_results]
    stages["backend2"] = {
        "status": "ok" if all(s in ("ok", "skipped") for s in b2_statuses) else "partial",
        "ms": round((time.perf_counter() - t0) * 1000),
        "endpoints": b2_statuses,
    }

    # Stage 5 — AI synthesis (must be last: reads all prior caches)
    t0 = time.perf_counter()
    try:
        summary = await refresh_ai_summary()
        stages["ai_summary"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        logger.warning("refresh/all stage 5 error: %s", exc)
        stages["ai_summary"] = {"status": "error", "detail": str(exc)}
        summary = {}

    # Stage 6 — Daily blog (Gemini — reads cached data from stages 1-2)
    t0 = time.perf_counter()
    blog_generated = False
    try:
        await refresh_daily_blog()
        stages["daily_blog"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
        blog_generated = True
    except Exception as exc:
        logger.warning("refresh/all stage 6 error: %s", exc)
        stages["daily_blog"] = {"status": "error", "detail": str(exc)}

    # Stage 7 — Blog review (Gemini — depends on Stage 6)
    if blog_generated:
        t0 = time.perf_counter()
        try:
            await refresh_blog_review()
            stages["blog_review"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
        except Exception as exc:
            logger.warning("refresh/all stage 7 error: %s", exc)
            stages["blog_review"] = {"status": "error", "detail": str(exc)}
    else:
        stages["blog_review"] = {"status": "skipped", "detail": "Stage 6 did not produce a blog"}

    total_ms = round((time.perf_counter() - overall_start) * 1000)
    logger.info("POST /refresh/all complete total_ms=%d", total_ms)
    return {
        "status": "refreshed",
        "date": summary.get("date"),
        "stages": stages,
        "total_ms": total_ms,
    }


# ── POST /refresh/intraday — Short-TTL refresh (noon + EOD, Mon-Fri) ─────────
@app.post("/refresh/intraday")
async def refresh_intraday(
    request: Request,
    skip_gemini: bool = Query(default=False, description="Skip Gemini sector analysis (EOD run)"),
    x_scheduler_token: Optional[str] = Header(default=None),
) -> dict:
    """Refresh short-TTL endpoints only. Called at 12:00 PM ET and 4:15 PM ET Mon-Fri.

    Skips industry (24h TTL), earnings (6h TTL), and ai_summary (to-midnight TTL).
    Pass skip_gemini=true for the EOD run to avoid a 3rd daily Gemini call.
    """
    _verify_scheduler(x_scheduler_token)
    logger.info("POST /refresh/intraday skip_gemini=%s", skip_gemini)
    stages: dict[str, dict] = {}
    overall_start = time.perf_counter()

    # Stage 1 — Concurrent: macro + news + morning (morning likely cache hit, 8h TTL)
    t0 = time.perf_counter()
    try:
        await asyncio.gather(
            get_morning_brief(),
            get_macro_pulse(),
            get_news_sentiment(),
        )
        stages["market_data"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        logger.warning("refresh/intraday stage 1 error: %s", exc)
        stages["market_data"] = {"status": "error", "detail": str(exc)}

    # Stage 2 — Concurrent: sector rotation + screener
    t0 = time.perf_counter()
    try:
        await asyncio.gather(
            get_sector_rotation(force_rule_based=skip_gemini),
            get_screener_data(),
        )
        stages["sector_screener"] = {
            "status": "ok",
            "ms": round((time.perf_counter() - t0) * 1000),
            "gemini_used": not skip_gemini,
        }
    except Exception as exc:
        logger.warning("refresh/intraday stage 2 error: %s", exc)
        stages["sector_screener"] = {"status": "error", "detail": str(exc)}

    # Stage 3 — Backend2 scan only (fibonacci 4h TTL still valid from morning)
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=35) as b2_client:
        scan_result = await _warm_backend2(b2_client, "/scan")
    stages["backend2_scan"] = {
        "status": scan_result["status"],
        "ms": round((time.perf_counter() - t0) * 1000),
    }

    total_ms = round((time.perf_counter() - overall_start) * 1000)
    logger.info("POST /refresh/intraday complete total_ms=%d", total_ms)
    return {"status": "refreshed", "stages": stages, "total_ms": total_ms}


# ── POST /refresh/ai-summary — Legacy endpoint (kept for backwards compat) ───
@app.post("/refresh/ai-summary")
async def refresh_ai_summary_endpoint(
    request: Request,
    x_scheduler_token: Optional[str] = Header(default=None),
) -> dict:
    """Legacy single-endpoint refresh. Prefer /refresh/all for full warm-up."""
    _verify_scheduler(x_scheduler_token)
    logger.info("POST /refresh/ai-summary (legacy) triggered")
    try:
        data = await refresh_ai_summary()
        return {"status": "refreshed", "date": data.get("date")}
    except Exception as exc:
        logger.exception("POST /refresh/ai-summary failed: %s", exc)
        raise HTTPException(status_code=503, detail="Refresh failed")


# ── Tool 10: Technical Signals (from shared Firestore analysis collection) ────
@app.get("/technical-signals")
async def technical_signals(
    request: Request,
    symbol: Optional[str] = Query(default=None, description="Single ticker, e.g. AAPL"),
) -> dict:
    logger.info("GET /technical-signals from %s symbol=%s", request.client, symbol)
    try:
        data = await get_technical_signals(symbol)
        logger.info("GET /technical-signals success")
        return data
    except Exception as exc:
        logger.exception("GET /technical-signals failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Tool 11: Industry Returns (from shared Firestore industry_cache) ──────────
@app.get("/industry-returns")
async def industry_returns(request: Request) -> dict:
    logger.info("GET /industry-returns from %s", request.client)
    try:
        data = await get_industry_returns()
        logger.info("GET /industry-returns success")
        return data
    except Exception as exc:
        logger.exception("GET /industry-returns failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── Admin: Seed / delta-update permanent ETF price history ───────────────────
@app.post("/admin/seed-etf-history")
async def seed_etf_history_endpoint(
    request: Request,
    x_scheduler_token: Optional[str] = Header(default=None),
) -> dict:
    """Seed or delta-update permanent ETF history for all 50 industries.

    - First run: fetches full yfinance history (max), stores in etf_history/*.
    - Subsequent runs: appends only new trading days (3mo fetch, delta filter).
    - Returns per-ETF row counts.

    Trigger manually once after deploy, then optionally add to /refresh/all.
    """
    _verify_scheduler(x_scheduler_token)
    logger.info("POST /admin/seed-etf-history triggered")
    try:
        results = await seed_etf_history()
        total = sum(results.values())
        logger.info("seed-etf-history complete: %d ETFs, %d total rows", len(results), total)
        return {"status": "ok", "etfs": len(results), "total_rows": total, "detail": results}
    except Exception as exc:
        logger.exception("POST /admin/seed-etf-history failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


# ── Tool 12: Market Summary (from shared Firestore summaries collection) ──────
@app.get("/market-summary")
async def market_summary(
    request: Request,
    days: int = Query(default=7, ge=1, le=30, description="Number of days of history"),
) -> dict:
    logger.info("GET /market-summary from %s days=%d", request.client, days)
    try:
        data = await get_market_summary(days)
        logger.info("GET /market-summary success")
        return data
    except Exception as exc:
        logger.exception("GET /market-summary failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
