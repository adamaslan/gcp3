"""GCP3 Backend2 — 7 deep-analysis tools missing from gcp3/backend.

Tools added here (not in gcp3/backend):
  /analyze/{symbol}     — 300-signal multi-timeframe analysis (4 TFs × ~79 signals)
  /fibonacci/{symbol}   — Swing high/low retracement + extension levels
  /trade-plan/{symbol}  — ATR-based stops, 1/2/3R targets, half-Kelly sizing
  /compare              — Head-to-head ranking of 2–6 symbols (12-indicator score)
  /portfolio-risk       — Sector breakdown, per-position VaR, concentration flag
  /options-risk/{symbol}— Black-Scholes chain (±10% strikes, 5 strikes)
  /scan                 — Top buy signals across a 20-stock universe

All endpoints: real data only (yfinance), HTTP 503 on failure, Firestore cache.
yfinance is synchronous — all fetches run in asyncio.to_thread.
"""
import asyncio
import logging
import re
from contextlib import asynccontextmanager as _acm

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analysis import (
    SECTOR_MAP,
    annual_vol,
    atr,
    bollinger,
    bs_greeks,
    consensus_signal,
    fetch,
    fetch_and_analyze,
    fibonacci_levels,
    full_analysis,
    kelly_fraction,
    macd,
    quick_score,
    rsi,
)
from cache import get_cache, set_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="GCP3 Backend2 — Deep Analysis", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _503(detail: str = "Service temporarily unavailable") -> HTTPException:
    return HTTPException(status_code=503, detail=detail)


# Allow uppercase letters and digits only; prevents Firestore document path traversal.
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,10}$")


def _sanitize_symbol(raw: str) -> str:
    """Validate and normalise a ticker symbol.

    Raises HTTP 400 if the value contains characters that could be used for
    Firestore document-ID path traversal (e.g. '/' or '..').

    Args:
        raw: Caller-supplied symbol string (path param or body field).

    Returns:
        Uppercase, stripped, validated symbol.

    Raises:
        HTTPException: 400 if the symbol does not match ``[A-Z0-9]{1,10}``.
    """
    clean = raw.upper().strip()
    if not _SYMBOL_RE.match(clean):
        raise HTTPException(
            status_code=400,
            detail="Invalid symbol: use 1–10 alphanumeric characters (e.g. AAPL, BRK)",
        )
    return clean


@_acm
async def _handled(location: str):
    """Async context manager: centralised error handling for data endpoints.

    - Re-raises ``HTTPException`` unchanged (e.g. 400 from ``_sanitize_symbol``).
    - Converts ``ValueError`` to HTTP 503 with the original message (yfinance
      errors are user-facing and do not contain sensitive internal details).
    - Logs and wraps all other exceptions in a generic HTTP 503 so internal
      stack traces / credentials are never returned to the caller.

    Args:
        location: Human-readable name used in log messages (e.g. "GET /analyze").
    """
    try:
        yield
    except HTTPException:
        raise
    except ValueError as exc:
        raise _503(str(exc))
    except Exception as exc:
        logger.exception("%s unexpected error: %s", location, type(exc).__name__)
        raise _503()


async def _fetch(symbol: str, period: str = "3mo"):
    """Run sync yfinance fetch in thread pool."""
    return await asyncio.to_thread(fetch, symbol, period)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "2.0.0", "tools": 7, "signals_per_analyze": "~300"}


# ── Tool 1: Multi-Timeframe Analysis (~300 signals) ──────────────────────────

# Approximate signal count per timeframe (non-None leaf values):
_SIGNALS_PER_TF: dict[str, int] = {
    "1mo": 62,   # SMA-50/100/200 unavailable (<50 bars)
    "3mo": 74,   # SMA-100/200 unavailable (<100 bars)
    "6mo": 77,   # SMA-200 unavailable (~126 bars; need ~200)
    "1y":  79,   # All indicators available (~252 bars)
}
_DEFAULT_PERIODS = ["1mo", "3mo", "6mo", "1y"]


@app.get("/analyze/{symbol}")
async def analyze(
    request: Request,
    symbol: str,
    period: str = Query(
        None,
        description="Single-timeframe override (1mo 3mo 6mo 1y). "
                    "Omit to run all 4 timeframes for ~300 signals.",
    ),
) -> dict:
    symbol    = _sanitize_symbol(symbol)   # ← path-traversal guard
    periods   = [period] if period else _DEFAULT_PERIODS
    cache_key = f"analyze2:{symbol}:{','.join(periods)}"
    logger.info("GET /analyze/%s periods=%s from %s", symbol, periods, request.client)
    if cached := get_cache(cache_key):
        return cached

    async with _handled(f"GET /analyze/{symbol}"):
        # Fetch + compute all ~79 indicators per timeframe in parallel
        raw = await asyncio.gather(
            *[asyncio.to_thread(fetch_and_analyze, symbol, p) for p in periods],
            return_exceptions=True,
        )

        timeframes: dict[str, dict] = {}
        failed_periods: list[str] = []
        for p, result in zip(periods, raw):
            if isinstance(result, Exception):
                # Log internally only — never echo exception text back to client
                logger.warning(
                    "GET /analyze/%s %s failed: %s", symbol, p, type(result).__name__
                )
                failed_periods.append(p)
            else:
                timeframes[p] = result

        if not timeframes:
            raise _503("Analysis unavailable — all timeframes returned no data")

        cs    = consensus_signal(timeframes)
        price = list(timeframes.values())[0]["price"]

        # Signal count: sum of per-TF estimates for successfully fetched timeframes
        total_signals = sum(_SIGNALS_PER_TF.get(p, 79) for p in timeframes)

        response = {
            "symbol":        symbol,
            "price":         price,
            "consensus":     cs,
            "timeframes":    timeframes,
            "total_signals": total_signals,
            "timeframe_key": {p: _SIGNALS_PER_TF.get(p, 79) for p in timeframes},
        }
        set_cache(cache_key, response, ttl_hours=1)
        logger.info(
            "GET /analyze/%s success signal=%s signals=%d tfs=%s",
            symbol, cs["signal"], total_signals, list(timeframes.keys()),
        )
        return response


# ── Tool 2: Fibonacci Retracement ────────────────────────────────────────────

@app.get("/fibonacci/{symbol}")
async def fibonacci(
    request: Request,
    symbol: str,
    period: str = Query("6mo", description="Longer period finds more meaningful swing points"),
) -> dict:
    symbol    = _sanitize_symbol(symbol)   # ← path-traversal guard
    cache_key = f"fib:{symbol}:{period}"
    logger.info("GET /fibonacci/%s period=%s from %s", symbol, period, request.client)
    if cached := get_cache(cache_key):
        return cached

    async with _handled(f"GET /fibonacci/{symbol}"):
        df = await _fetch(symbol, period)
        close  = df["Close"]
        price  = float(close.iloc[-1])
        high   = float(df["High"].max())
        low    = float(df["Low"].min())
        levels = fibonacci_levels(high, low)

        sorted_vals = sorted(levels.values())
        above = [v for v in sorted_vals if v > price]
        below = [v for v in sorted_vals if v <= price]

        result = {
            "symbol":             symbol,
            "price":              round(price, 4),
            "swing_high":         round(high, 4),
            "swing_low":          round(low, 4),
            "levels":             levels,
            "nearest_support":    round(max(below), 4) if below else round(low, 4),
            "nearest_resistance": round(min(above), 4) if above else round(high, 4),
        }
        set_cache(cache_key, result, ttl_hours=4)
        logger.info("GET /fibonacci/%s success", symbol)
        return result


# ── Tool 3: Trade Plan ────────────────────────────────────────────────────────

@app.get("/trade-plan/{symbol}")
async def trade_plan(
    request: Request,
    symbol: str,
    win_rate: float = Query(0.55, ge=0.0, le=1.0, description="Historical win rate for Kelly sizing"),
) -> dict:
    symbol    = _sanitize_symbol(symbol)   # ← path-traversal guard
    cache_key = f"trade:{symbol}"
    logger.info("GET /trade-plan/%s win_rate=%.2f from %s", symbol, win_rate, request.client)
    if cached := get_cache(cache_key):
        return cached

    async with _handled(f"GET /trade-plan/{symbol}"):
        df = await _fetch(symbol, "3mo")
        close   = df["Close"]
        price   = float(close.iloc[-1])
        atr_val = atr(df)

        # ATR-based stop: 1.5× ATR below entry (wider than 1× to avoid noise)
        stop      = round(price - atr_val * 1.5, 4)
        risk_r    = price - stop                      # 1R in dollars
        target_1r = round(price + risk_r * 1, 4)
        target_2r = round(price + risk_r * 2, 4)
        target_3r = round(price + risk_r * 3, 4)

        sig = await asyncio.to_thread(quick_score, df)
        # Half-Kelly assuming 2R average win, 1R average loss
        kelly = kelly_fraction(win_rate, avg_win_r=2.0, avg_loss_r=1.0)

        result = {
            "symbol":         symbol,
            "price":          round(price, 4),
            "signal":         sig["signal"],
            "entry":          round(price, 4),
            "stop_loss":      stop,
            "targets":        {"1r": target_1r, "2r": target_2r, "3r": target_3r},
            "risk_per_share": round(risk_r, 4),
            "atr":            round(atr_val, 4),
            # Kelly: fraction of total capital to risk on this trade
            "kelly_fraction": kelly,
            "kelly_note":     "Half-Kelly applied (full × 0.5) to reduce risk of ruin",
        }
        set_cache(cache_key, result, ttl_hours=1)
        logger.info("GET /trade-plan/%s success", symbol)
        return result


# ── Tool 4: Compare Securities ───────────────────────────────────────────────

class CompareRequest(BaseModel):
    symbols: list[str]
    period: str = "3mo"


@app.post("/compare")
async def compare(request: Request, body: CompareRequest) -> dict:
    logger.info("POST /compare symbols=%s from %s", body.symbols, request.client)
    if not (2 <= len(body.symbols) <= 6):
        raise HTTPException(status_code=400, detail="Provide 2–6 symbols")

    # Validate all symbols up-front; return 400 rather than silently skipping
    sanitized_symbols = [_sanitize_symbol(s) for s in body.symbols]

    async def _one(sym: str) -> dict:
        try:
            df    = await _fetch(sym, body.period)
            close = df["Close"]
            price = float(close.iloc[-1])
            # quick_score uses all 12 indicators for consistent ranking
            sig   = await asyncio.to_thread(quick_score, df)
            m     = macd(close)
            bb    = bollinger(close)
            return {
                "symbol":        sym.upper(),
                "price":         round(price, 4),
                "period_return": round((price / float(close.iloc[0]) - 1) * 100, 2),
                "rsi":           rsi(close, 14) or 0.0,
                "macd_trend":    m["trend"],
                "bb_position":   bb["position"],
                "signal":        sig["signal"],
                "score":         sig["score"],
                "confidence":    sig["confidence"],
            }
        except Exception:
            return {"symbol": sym.upper(), "error": "unavailable"}

    results = list(await asyncio.gather(*[_one(s) for s in sanitized_symbols]))
    ranked  = sorted(
        [r for r in results if "error" not in r],
        key=lambda x: x["score"],
        reverse=True,
    )
    logger.info("POST /compare success leader=%s", ranked[0]["symbol"] if ranked else "none")
    return {"period": body.period, "leader": ranked[0] if ranked else None, "ranked": ranked}


# ── Tool 5: Portfolio Risk ────────────────────────────────────────────────────

class Position(BaseModel):
    symbol: str
    shares: float
    avg_cost: float


class PortfolioRequest(BaseModel):
    positions: list[Position]


@app.post("/portfolio-risk")
async def portfolio_risk(request: Request, body: PortfolioRequest) -> dict:
    logger.info("POST /portfolio-risk positions=%d from %s", len(body.positions), request.client)

    # Validate all symbols up-front; raises HTTP 400 on invalid input
    for p in body.positions:
        p.symbol = _sanitize_symbol(p.symbol)

    async def _pos(p: Position) -> dict:
        try:
            df    = await _fetch(p.symbol, "1mo")
            close = df["Close"]
            price = float(close.iloc[-1])
            vol   = annual_vol(close)
            value = round(price * p.shares, 2)
            return {
                "symbol":     p.symbol.upper(),
                "shares":     p.shares,
                "price":      round(price, 4),
                "value":      value,
                "cost":       round(p.avg_cost * p.shares, 2),
                "pnl_pct":    round((price / p.avg_cost - 1) * 100, 2),
                "annual_vol": round(vol, 4),
                "sector":     SECTOR_MAP.get(p.symbol.upper(), "Other"),
            }
        except Exception:
            return {"symbol": p.symbol.upper(), "error": "unavailable"}

    positions = list(await asyncio.gather(*[_pos(p) for p in body.positions]))
    valid     = [p for p in positions if "error" not in p]

    total_value = sum(p["value"] for p in valid)
    if total_value == 0:
        raise _503("No valid positions — check symbols and retry")

    # Sector concentration
    sector_totals: dict[str, float] = {}
    for p in valid:
        sector_totals[p["sector"]] = sector_totals.get(p["sector"], 0) + p["value"]
    sector_pct = {k: round(v / total_value * 100, 1) for k, v in sector_totals.items()}

    # Portfolio volatility: weighted average (conservative — ignores diversification benefit)
    port_annual_vol = sum(p["annual_vol"] * p["value"] / total_value for p in valid)
    daily_vol = port_annual_vol / (252 ** 0.5)

    # Parametric VaR (95% one-day, normal distribution)
    var_95_daily = round(total_value * daily_vol * 1.645, 2)

    result = {
        "total_value":        round(total_value, 2),
        "positions":          valid,
        "sector_breakdown":   sector_pct,
        "port_annual_vol":    round(port_annual_vol, 4),
        "var_95_daily":       var_95_daily,
        "var_95_note":        "Parametric VaR at 95% confidence, assumes normal returns, no correlation adjustment",
        "concentration_risk": max(sector_pct.values(), default=0) > 40,
    }
    logger.info(
        "POST /portfolio-risk success total=%.0f var95=%.0f concentration=%s",
        total_value, var_95_daily, result["concentration_risk"],
    )
    return result


# ── Tool 6: Options Risk ──────────────────────────────────────────────────────

@app.get("/options-risk/{symbol}")
async def options_risk(
    request: Request,
    symbol: str,
    expiry_days: int = Query(30, ge=1, le=365, description="Calendar days to expiry"),
    risk_free_rate: float = Query(0.05, description="Annualised risk-free rate"),
) -> dict:
    symbol    = _sanitize_symbol(symbol)   # ← path-traversal guard
    cache_key = f"options:{symbol}:{expiry_days}"
    logger.info("GET /options-risk/%s expiry=%d from %s", symbol, expiry_days, request.client)
    if cached := get_cache(cache_key):
        return cached

    async with _handled(f"GET /options-risk/{symbol}"):
        df    = await _fetch(symbol, "1mo")
        close = df["Close"]
        price = float(close.iloc[-1])
        vol   = annual_vol(close)      # historical vol as IV proxy
        T     = expiry_days / 365.0

        # Build chain: ATM ± 10% in 5% increments
        strikes = [round(price * m, 2) for m in [0.90, 0.95, 1.00, 1.05, 1.10]]
        chain = [
            {
                "strike":    K,
                "moneyness": round((K - price) / price * 100, 1),
                "call":      bs_greeks(price, K, T, risk_free_rate, vol, call=True),
                "put":       bs_greeks(price, K, T, risk_free_rate, vol, call=False),
            }
            for K in strikes
        ]

        result = {
            "symbol":         symbol,
            "price":          round(price, 4),
            "hist_vol":       round(vol, 4),
            "expiry_days":    expiry_days,
            "risk_free_rate": risk_free_rate,
            "chain":          chain,
            "vol_note":       "IV estimated from 1-month historical volatility — for indicative purposes only",
        }
        set_cache(cache_key, result, ttl_hours=1)
        logger.info("GET /options-risk/%s success hist_vol=%.2f", symbol, vol)
        return result


# ── Tool 7: Trade Scanner ─────────────────────────────────────────────────────

_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "JPM",  "BAC",  "GLD",   "SPY",  "QQQ",  "AMD",  "NFLX",
    "CRWD", "INTC", "CRM",   "ADBE", "PYPL", "SHOP",
]


@app.get("/scan")
async def scan(
    request: Request,
    limit: int = Query(10, ge=1, le=20, description="Max buy signals to return"),
) -> dict:
    logger.info("GET /scan limit=%d from %s", limit, request.client)
    cache_key = f"scan:universe:{limit}"
    if cached := get_cache(cache_key):
        return cached

    async def _one(sym: str) -> dict | None:
        try:
            df    = await _fetch(sym, "3mo")
            close = df["Close"]
            sig   = await asyncio.to_thread(quick_score, df)
            return {
                "symbol":     sym,
                "price":      round(float(close.iloc[-1]), 4),
                "signal":     sig["signal"],
                "score":      sig["score"],
                "confidence": sig["confidence"],
                "rsi":        rsi(close, 14) or 0.0,
                "reasons":    sig["reasons"],
            }
        except Exception:
            return None

    results = [r for r in await asyncio.gather(*[_one(s) for s in _UNIVERSE]) if r]
    buy_signals = sorted(
        [r for r in results if r["score"] > 0],
        key=lambda x: x["score"],
        reverse=True,
    )

    result = {
        "universe_size": len(_UNIVERSE),
        "scanned":       len(results),
        "buy_signals":   buy_signals[:limit],
    }
    set_cache(cache_key, result, ttl_hours=1)
    logger.info("GET /scan success found=%d buys", len(buy_signals))
    return result
