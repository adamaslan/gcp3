"""Feature #22 — Cross-Asset Signals (Rates ↔ Equities).

Sources: FRED (DGS10, DGS2, DGS3MO), yfinance (DXY, Gold), FRED (BAMLH0A0HYM2).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = ""  # free, no key required for basic observations

YieldCurveShape = Literal["steep", "flat", "inverted", "normal"]
CreditStress = Literal["low", "moderate", "elevated", "extreme"]


@dataclass
class CrossAssetSignals:
    dgs10: float | None
    dgs2: float | None
    dgs3mo: float | None
    yield_curve_2s10s: float | None       # dgs10 - dgs2
    yield_curve_shape: YieldCurveShape
    yield_curve_regime_cue: str
    dxy_level: float | None
    dxy_5d_change_pct: float | None
    dxy_equity_correlation: float | None  # rolling 20d
    gold_price: float | None
    gold_5d_change_pct: float | None
    gold_divergence: bool                 # gold up + equities down = risk-off signal
    hy_oas: float | None                  # high-yield OAS in bps
    credit_stress: CreditStress


async def _fred_latest(series_id: str) -> float | None:
    url = (
        f"{FRED_BASE}?series_id={series_id}&api_key={FRED_API_KEY}"
        f"&file_type=json&limit=1&sort_order=desc"
    )
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url)
            obs = resp.json().get("observations", [{}])
            val = obs[0].get("value", ".")
            return float(val) if val != "." else None
    except Exception as e:
        logger.warning("fred_fetch_failed series=%s error=%s", series_id, e)
        return None


def _classify_yield_curve(spread: float | None) -> YieldCurveShape:
    if spread is None:
        return "normal"
    if spread > 1.5:
        return "steep"
    if spread > 0.0:
        return "normal"
    if spread > -0.5:
        return "flat"
    return "inverted"


def _yield_curve_cue(shape: YieldCurveShape, spread: float | None) -> str:
    if shape == "inverted":
        return f"Inverted yield curve (2s10s={spread:.2f}%) — recession signal. Risk-off bias."
    if shape == "flat":
        return f"Flat curve (2s10s={spread:.2f}%) — late-cycle caution. Watch credit spreads."
    if shape == "steep":
        return f"Steep curve (2s10s={spread:.2f}%) — early-cycle recovery signal. Risk-on bias."
    return f"Normal yield curve (2s10s={spread:.2f}%)."


def _classify_credit_stress(hy_oas: float | None) -> CreditStress:
    if hy_oas is None:
        return "moderate"
    if hy_oas < 300:
        return "low"
    if hy_oas < 500:
        return "moderate"
    if hy_oas < 800:
        return "elevated"
    return "extreme"


async def fetch_cross_asset_signals(spy_5d_return: float | None = None) -> CrossAssetSignals:
    """Fetch cross-asset signals from FRED and yfinance.

    Args:
        spy_5d_return: SPY 5-day return for gold divergence check (optional).

    Returns:
        CrossAssetSignals dataclass.
    """
    dgs10, dgs2, dgs3mo, hy_oas = await asyncio.gather(
        _fred_latest("DGS10"),
        _fred_latest("DGS2"),
        _fred_latest("DGS3MO"),
        _fred_latest("BAMLH0A0HYM2"),
    )

    spread = round(dgs10 - dgs2, 4) if dgs10 is not None and dgs2 is not None else None
    curve_shape = _classify_yield_curve(spread)
    curve_cue = _yield_curve_cue(curve_shape, spread)

    dxy_level = dxy_change = gold_price = gold_change = dxy_equity_corr = None
    gold_divergence = False
    try:
        import yfinance as yf
        data = yf.download(["DX-Y.NYB", "GC=F"], period="30d", progress=False, auto_adjust=True)["Close"]
        if "DX-Y.NYB" in data.columns and len(data) >= 6:
            dxy_series = data["DX-Y.NYB"].dropna()
            dxy_level = round(float(dxy_series.iloc[-1]), 3)
            dxy_change = round((dxy_series.iloc[-1] / dxy_series.iloc[-6] - 1) * 100, 4)
        if "GC=F" in data.columns and len(data) >= 6:
            gold_series = data["GC=F"].dropna()
            gold_price = round(float(gold_series.iloc[-1]), 2)
            gold_change = round((gold_series.iloc[-1] / gold_series.iloc[-6] - 1) * 100, 4)
        # Gold up + equities down = risk-off signal
        if gold_change is not None and spy_5d_return is not None:
            gold_divergence = gold_change > 1.0 and spy_5d_return < -1.0
    except Exception as e:
        logger.warning("cross_asset_yfinance_failed error=%s", e)

    credit_stress = _classify_credit_stress(hy_oas)

    return CrossAssetSignals(
        dgs10=dgs10, dgs2=dgs2, dgs3mo=dgs3mo,
        yield_curve_2s10s=spread, yield_curve_shape=curve_shape,
        yield_curve_regime_cue=curve_cue,
        dxy_level=dxy_level, dxy_5d_change_pct=dxy_change,
        dxy_equity_correlation=dxy_equity_corr,
        gold_price=gold_price, gold_5d_change_pct=gold_change,
        gold_divergence=gold_divergence,
        hy_oas=hy_oas, credit_stress=credit_stress,
    )


def format_cross_asset_for_prompt(s: CrossAssetSignals) -> str:
    """Format cross-asset signals for inclusion in an LLM prompt."""
    return (
        f"Cross-Asset: 10y={s.dgs10}% 2y={s.dgs2}% 3mo={s.dgs3mo}% "
        f"2s10s={s.yield_curve_2s10s} curve={s.yield_curve_shape} ({s.yield_curve_regime_cue}) "
        f"DXY={s.dxy_level} DXY_5d={s.dxy_5d_change_pct}% "
        f"Gold={s.gold_price} Gold_5d={s.gold_5d_change_pct}% gold_divergence={s.gold_divergence} "
        f"HY_OAS={s.hy_oas}bps credit_stress={s.credit_stress}"
    )
