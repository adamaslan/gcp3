"""GCP3 Finance API — 8 consolidated public endpoints."""
import asyncio
import logging
import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from industry import compute_returns, get_industry_data, seed_etf_history
from morning import get_morning_brief
from screener import get_screener_data
from sector_rotation import get_sector_rotation
from earnings_radar import get_earnings_radar
from macro_pulse import get_macro_pulse
from news_sentiment import get_news_sentiment
from ai_summary import get_ai_summary, refresh_ai_summary
from technical_signals import get_technical_signals
from industry_returns import get_industry_returns
from market_summary import get_market_summary
from daily_blog import get_daily_blog, refresh_daily_blog
from blog_reviewer import get_blog_review, refresh_blog_review
from correlation_article import get_correlation_article, refresh_correlation_article
from firestore import db as firestore_db
from data_client import fh_429_stats
from datetime import date, datetime, timezone

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


@app.get("/debug/status")
def debug_status() -> dict:
    """Live diagnostic snapshot for the backend-debug command.

    Returns:
      - route_inventory: all registered GET/POST routes (detects deployed-code drift)
      - industry_cache: doc count + most-stale updated timestamp (detects rate-limit stalls)
      - rate_limits: Finnhub 429 rolling counter from this instance
      - gcp3_cache: count of live (non-expired) cache docs
    """
    now = datetime.now(timezone.utc)

    # Route inventory — the definitive list of what's actually registered
    routes = sorted(
        [r.path for r in app.routes if hasattr(r, "path") and r.path not in ("/openapi.json", "/docs", "/redoc")]
    )

    # industry_cache freshness
    try:
        ic_docs = list(firestore_db().collection("industry_cache").stream())
        ic_count = len(ic_docs)
        updated_times = [
            d.to_dict().get("updated") for d in ic_docs
            if d.to_dict().get("updated")
        ]
        # updated is stored as ISO string
        ic_oldest_updated = min(updated_times) if updated_times else None
        ic_newest_updated = max(updated_times) if updated_times else None
        # Age in hours of the newest write (how stale is the freshest doc?)
        ic_freshness_hours: float | None = None
        if ic_newest_updated:
            try:
                newest_dt = datetime.fromisoformat(ic_newest_updated)
                if newest_dt.tzinfo is None:
                    newest_dt = newest_dt.replace(tzinfo=timezone.utc)
                ic_freshness_hours = round((now - newest_dt).total_seconds() / 3600, 2)
            except Exception:
                pass
    except Exception as exc:
        ic_count = -1
        ic_oldest_updated = ic_newest_updated = None
        ic_freshness_hours = None
        logger.warning("debug_status: industry_cache read failed: %s", exc)

    # gcp3_cache live doc count
    try:
        live_cache_docs = list(
            firestore_db().collection("gcp3_cache")
            .where("expires_at", ">", now)
            .limit(200)
            .stream()
        )
        live_cache_keys = [d.id for d in live_cache_docs]
    except Exception as exc:
        live_cache_keys = []
        logger.warning("debug_status: gcp3_cache read failed: %s", exc)

    # Expected consolidated routes (POST-consolidation set)
    expected_routes = {"/industry-intel", "/signals", "/industry-returns", "/screener",
                       "/market-overview", "/content", "/macro-pulse"}
    missing_routes = sorted(expected_routes - set(routes))

    logger.info(
        "debug_status: routes=%d industry_cache_docs=%d ic_freshness_h=%s missing_routes=%s",
        len(routes), ic_count, ic_freshness_hours, missing_routes or "none",
    )

    return {
        "timestamp": now.isoformat(),
        "today": str(date.today()),
        "route_inventory": routes,
        "missing_expected_routes": missing_routes,
        "industry_cache": {
            "doc_count": ic_count,
            "newest_updated": ic_newest_updated,
            "oldest_updated": ic_oldest_updated,
            "freshness_hours": ic_freshness_hours,
            "stale": ic_freshness_hours is not None and ic_freshness_hours > 25,
        },
        "rate_limits": {
            "finnhub_429s": fh_429_stats(),
        },
        "gcp3_cache": {
            "live_doc_count": len(live_cache_keys),
            "live_keys": live_cache_keys,
        },
    }


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
async def compute_returns_endpoint(request: Request) -> dict:
    """Precompute multi-period returns from stored ETF history into industry_cache.

    Zero Finnhub or Alpha Vantage calls. Safe to run hourly or daily via
    Cloud Scheduler. Must run after seed-etf-history has populated etf_store.
    """
    _verify_scheduler(request)
    logger.info("POST /admin/compute-returns triggered")
    try:
        result = await compute_returns()
        return result
    except Exception as exc:
        logger.exception("POST /admin/compute-returns failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


# ── Admin: Purge expired cache (safety net for native TTL) ─────────────────────
@app.post("/admin/purge-cache")
async def purge_expired_cache(request: Request) -> dict:
    """Delete expired documents from gcp3_cache collection.

    Runs nightly as a safety net alongside native Firestore TTL (Phase 1A).
    Batches deletes to stay under Firestore's 500-operation batch limit.
    Called by Cloud Scheduler at 2:00 AM ET (6:00 AM UTC).

    Returns:
        {"deleted": int, "timestamp": ISO string}
    """
    _verify_scheduler(request)
    logger.info("POST /admin/purge-cache triggered")
    now = datetime.now(timezone.utc)
    deleted = 0
    batch = firestore_db().batch()
    batch_count = 0

    try:
        # Loop until no more expired docs remain (each pass handles up to 450)
        while True:
            query = (
                firestore_db().collection("gcp3_cache")
                .where("expires_at", "<", now)
                .limit(450)
            )
            snaps = list(query.stream())
            if not snaps:
                break
            for snap in snaps:
                batch.delete(snap.reference)
                batch_count += 1
                deleted += 1
                if batch_count >= 450:
                    batch.commit()
                    batch = firestore_db().batch()
                    batch_count = 0

        if batch_count > 0:
            batch.commit()

        logger.info("purge-cache: deleted %d expired documents", deleted)
        return {"deleted": deleted, "timestamp": now.isoformat()}
    except Exception as exc:
        logger.exception("POST /admin/purge-cache failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


# ── Stock Screener (kept — standalone, no overlap) ────────────────────────────
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


# ── Earnings Radar (kept — used internally by /market-overview + /macro proxy) ─
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


# ── Macro Pulse (kept — used internally by /macro proxy) ─────────────────────
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


# ── Scheduler auth helper ─────────────────────────────────────────────────────
_EXPECTED_AUDIENCE = "https://gcp3-backend-cif7ppahzq-uc.a.run.app"
_EXPECTED_SA = "gcp3-scheduler@ttb-lang1.iam.gserviceaccount.com"

def _verify_scheduler(request: Request) -> None:
    """Verify Cloud Scheduler OIDC token from Authorization header.

    Validates:
    - Token is a valid Google-signed JWT
    - Audience matches this Cloud Run service URL
    - Email claim matches the dedicated scheduler service account
    Raises 401 on any failure. Falls back to SCHEDULER_SECRET env var for
    local/manual testing when the Authorization header is absent.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer = auth_header[len("Bearer "):]
        try:
            claims = google_id_token.verify_oauth2_token(
                bearer,
                google_requests.Request(),
                audience=_EXPECTED_AUDIENCE,
            )
        except Exception as exc:
            logger.warning("Scheduler OIDC token verification failed: %s", exc)
            raise HTTPException(status_code=401, detail="Unauthorized")
        if claims.get("email") != _EXPECTED_SA:
            logger.warning("Scheduler token email mismatch: %s", claims.get("email"))
            raise HTTPException(status_code=401, detail="Unauthorized")
        return

    # Fallback: shared secret for local curl / manual testing only
    secret = os.environ.get("SCHEDULER_SECRET")
    manual_token = request.headers.get("X-Scheduler-Token")
    if not secret or manual_token != secret:
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


# ── POST /refresh/premarket — Pre-market warmup (Cloud Scheduler, 8:30 AM ET) ──
@app.post("/refresh/premarket")
async def refresh_premarket(request: Request) -> dict:
    """Lightweight pre-market cache warm-up for early users (8:30 AM ET).

    Only warms endpoints that don't require heavy computation:
    - morning_brief (news summary, lightweight)
    - news_sentiment (social sentiment, lightweight)
    - macro_pulse (macro indicators, lightweight)

    Skips industry tracker (50 Finnhub calls), earnings radar, and AI synthesis.
    Runs 1 hour before the full morning refresh to ensure data is ready for
    early-bird traders.
    """
    _verify_scheduler(request)
    logger.info("POST /refresh/premarket started")
    stages: dict[str, dict] = {}
    overall_start = time.perf_counter()

    # Lightweight endpoints only — no heavy computation
    t0 = time.perf_counter()
    try:
        await asyncio.gather(
            get_morning_brief(),
            get_news_sentiment(),
            get_macro_pulse(),
        )
        stages["lightweight_data"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        logger.warning("refresh/premarket error: %s", exc)
        stages["lightweight_data"] = {"status": "error", "detail": str(exc)}

    total_ms = round((time.perf_counter() - overall_start) * 1000)
    logger.info("POST /refresh/premarket complete total_ms=%d", total_ms)
    return {
        "status": "premarket_warmed",
        "stages": stages,
        "total_ms": total_ms,
    }


# ── POST /refresh/all — Morning full warm-up (Cloud Scheduler, 9:35 AM ET) ───
@app.post("/refresh/all")
async def refresh_all(request: Request) -> dict:
    """Full cache warm-up in dependency order. Called by Cloud Scheduler at 9:35 AM ET Mon-Fri.

    Stages:
        0  Firestore readers — validate pipeline data is present (zero API cost)
        1  Independent market data — concurrent Finnhub calls
        2  Sector + screener — concurrent (Finnhub + Gemini)
        3  Industry — isolated to stay under Alpha Vantage 25-call/day limit
        4  Backend2 fan-out — scan + key Fibonacci levels via yfinance (no Finnhub quota)
        5  AI synthesis — must run last; aggregates all prior warm caches
    """
    _verify_scheduler(request)
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

    # Stage 3b — Recompute multi-period returns from etf_store → industry_cache
    t0 = time.perf_counter()
    try:
        await compute_returns()
        stages["compute_returns"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        logger.warning("refresh/all stage 3b error: %s", exc)
        stages["compute_returns"] = {"status": "error", "detail": str(exc)}

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

    # Stage 8 — Correlation article (Gemini — reads all caches, generates article)
    t0 = time.perf_counter()
    try:
        await refresh_correlation_article()
        stages["correlation_article"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        logger.warning("refresh/all stage 8 error: %s", exc)
        stages["correlation_article"] = {"status": "error", "detail": str(exc)}

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
) -> dict:
    """Refresh short-TTL endpoints only. Called at 12:00 PM ET and 4:15 PM ET Mon-Fri.

    Skips industry (24h TTL), earnings (6h TTL), and ai_summary (to-midnight TTL).
    Pass skip_gemini=true for the EOD run to avoid a 3rd daily Gemini call.
    """
    _verify_scheduler(request)
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
async def refresh_ai_summary_endpoint(request: Request) -> dict:
    """Legacy single-endpoint refresh. Prefer /refresh/all for full warm-up."""
    _verify_scheduler(request)
    logger.info("POST /refresh/ai-summary (legacy) triggered")
    try:
        data = await refresh_ai_summary()
        return {"status": "refreshed", "date": data.get("date")}
    except Exception as exc:
        logger.exception("POST /refresh/ai-summary failed: %s", exc)
        raise HTTPException(status_code=503, detail="Refresh failed")


# ── Industry Returns (kept — still used by /industry-returns page directly) ───
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
async def seed_etf_history_endpoint(request: Request) -> dict:
    """Seed or delta-update permanent ETF history for all 50 industries.

    - First run: fetches full yfinance history (max), stores in etf_history/*.
    - Subsequent runs: appends only new trading days (3mo fetch, delta filter).
    - Returns per-ETF row counts.

    Trigger manually once after deploy, then optionally add to /refresh/all.
    """
    _verify_scheduler(request)
    logger.info("POST /admin/seed-etf-history triggered")
    try:
        results = await seed_etf_history()
        total = sum(results.values())
        logger.info("seed-etf-history complete: %d ETFs, %d total rows", len(results), total)
        return {"status": "ok", "etfs": len(results), "total_rows": total, "detail": results}
    except Exception as exc:
        logger.exception("POST /admin/seed-etf-history failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# CONSOLIDATED ENDPOINTS (API Consolidation — 17 → 8)
# ═══════════════════════════════════════════════════════════════════════════════

# ── /industry-intel: replaces /industry-tracker + /industry-quotes ────────────
@app.get("/industry-intel")
async def industry_intel(
    request: Request,
    view: str = Query(default="full", description="'compact' returns only sector/etf/price/change_pct"),
) -> dict:
    """Today's industry-level market intelligence.

    Merges live quotes, sector heatmap, and leaders/laggards into one payload.
    Replaces /industry-tracker and /industry-quotes.
    """
    logger.info("GET /industry-intel view=%s from %s", view, request.client)
    try:
        data = await get_industry_data()
        if view == "compact":
            data = _compact_quotes(data)
        logger.info("GET /industry-intel success")
        return data
    except Exception as exc:
        logger.exception("GET /industry-intel failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── /signals: replaces /technical-signals, adds ?scope=industries ─────────────
@app.get("/signals")
async def signals(
    request: Request,
    symbol: Optional[str] = Query(default=None, description="Single ticker, e.g. AAPL"),
    scope: Optional[str] = Query(default=None, description="'industries' returns industry-level signal aggregation"),
) -> dict:
    """Signals hub: per-ticker AI signals and/or industry-level signal aggregation.

    GET /signals                  → all ticker signals
    GET /signals?symbol=AAPL      → single ticker
    GET /signals?scope=industries → industry-level signal summary (bullish/bearish counts)
    """
    logger.info("GET /signals symbol=%s scope=%s from %s", symbol, scope, request.client)
    try:
        if scope == "industries":
            ticker_signals, industry_data = await asyncio.gather(
                get_technical_signals(symbol),
                get_industry_data(),
            )
            sector_summary = _compute_industry_signal_summary(industry_data)
            data = {**ticker_signals, "industry_signals": sector_summary}
        else:
            data = await get_technical_signals(symbol)
        logger.info("GET /signals success")
        return data
    except Exception as exc:
        logger.exception("GET /signals failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


def _compute_industry_signal_summary(industry_data: dict) -> dict:
    """Aggregate industry ETF data into per-sector signal counts.

    Uses change_pct as a simple directional proxy: >0 = bullish, <0 = bearish.
    Full MA/RSI computation would require etf_store price history (future enhancement).
    """
    by_sector: dict[str, dict] = {}
    for name, info in industry_data.get("industries", {}).items():
        sector = info.get("sector", "Unknown")
        change_pct = info.get("change_pct") or 0.0
        if sector not in by_sector:
            by_sector[sector] = {"bullish": 0, "bearish": 0, "neutral": 0, "industries": []}
        direction = "bullish" if change_pct > 0 else ("bearish" if change_pct < 0 else "neutral")
        by_sector[sector][direction] += 1
        by_sector[sector]["industries"].append({
            "industry": name,
            "etf": info.get("etf"),
            "change_pct": change_pct,
            "direction": direction,
        })
    return by_sector


# ── /market-overview: replaces /morning-brief + /ai-summary + /news-sentiment + /market-summary ──
@app.get("/market-overview")
async def market_overview(
    request: Request,
    sections: Optional[str] = Query(
        default=None,
        description="Comma-separated subset: brief,ai_summary,sentiment,history",
    ),
    days: int = Query(default=7, ge=1, le=30, description="History days for the 'history' section"),
) -> dict:
    """Daily market narrative combining morning brief, AI summary, news sentiment, and history.

    GET /market-overview                           → all sections
    GET /market-overview?sections=brief,sentiment  → specific sections only
    """
    logger.info("GET /market-overview sections=%s from %s", sections, request.client)

    requested = set(sections.split(",")) if sections else {"brief", "ai_summary", "sentiment", "history"}

    tasks: dict[str, object] = {}
    if "brief" in requested:
        tasks["brief"] = get_morning_brief()
    if "ai_summary" in requested:
        tasks["ai_summary"] = get_ai_summary()
    if "sentiment" in requested:
        tasks["sentiment"] = get_news_sentiment()
    if "history" in requested:
        tasks["history"] = get_market_summary(days)

    try:
        keys = list(tasks.keys())
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        payload: dict = {"sections_included": keys}
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                logger.warning("market-overview section %s failed: %s", key, result)
                payload[key] = {"error": str(result)}
            else:
                payload[key] = result
        logger.info("GET /market-overview success sections=%s", keys)
        return payload
    except Exception as exc:
        logger.exception("GET /market-overview failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


# ── /content: replaces /daily-blog + /blog-review + /correlation-article ─────
@app.get("/content")
async def content(
    request: Request,
    type: Optional[str] = Query(
        default=None,
        description="Content type: 'blog', 'review', or 'correlation'. Omit for all.",
    ),
) -> dict:
    """Content feed: AI-generated articles via ?type=blog|review|correlation.

    GET /content?type=blog         → was /daily-blog
    GET /content?type=review       → was /blog-review
    GET /content?type=correlation  → was /correlation-article
    GET /content                   → latest of each type
    """
    logger.info("GET /content type=%s from %s", type, request.client)
    try:
        if type == "blog":
            return await get_daily_blog()
        if type == "review":
            return await get_blog_review()
        if type == "correlation":
            return await get_correlation_article()

        # No type param — return all three concurrently
        blog, review, correlation = await asyncio.gather(
            get_daily_blog(),
            get_blog_review(),
            get_correlation_article(),
            return_exceptions=True,
        )
        return {
            "blog": blog if not isinstance(blog, Exception) else {"error": str(blog)},
            "review": review if not isinstance(review, Exception) else {"error": str(review)},
            "correlation": correlation if not isinstance(correlation, Exception) else {"error": str(correlation)},
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("GET /content failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
