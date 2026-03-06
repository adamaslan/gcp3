"""GCP3 Finance API - 12 MCP tools (9 Finnhub + 3 shared Firestore)."""
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from industry import get_industry_data
from morning import get_morning_brief
from screener import get_screener_data
from sector_rotation import get_sector_rotation
from earnings_radar import get_earnings_radar
from macro_pulse import get_macro_pulse
from news_sentiment import get_news_sentiment
from portfolio_analyzer import get_portfolio_analysis
from ai_summary import get_ai_summary
from technical_signals import get_technical_signals
from industry_returns import get_industry_returns
from market_summary import get_market_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="GCP3 Finance API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


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
        raise HTTPException(status_code=503, detail=str(exc))


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
        raise HTTPException(status_code=503, detail=str(exc))


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
        raise HTTPException(status_code=503, detail=str(exc))


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
        raise HTTPException(status_code=503, detail=str(exc))


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
        raise HTTPException(status_code=503, detail=str(exc))


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
        raise HTTPException(status_code=503, detail=str(exc))


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
        raise HTTPException(status_code=503, detail=str(exc))


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
        raise HTTPException(status_code=503, detail=str(exc))


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
        raise HTTPException(status_code=503, detail=str(exc))


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
        raise HTTPException(status_code=503, detail=str(exc))
