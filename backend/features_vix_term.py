"""Feature #21 — VIX Term Structure.

Fetches ^VIX9D, ^VIX, ^VIX3M, ^VIX6M from Yahoo Finance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

VIX_TICKERS = {"vix_9d": "^VIX9D", "vix_spot": "^VIX", "vix_3m": "^VIX3M", "vix_6m": "^VIX6M"}

TermShape = Literal[
    "contango",
    "flat",
    "backwardation_mild",
    "backwardation_severe",
    "inverted_9d_spot",
]


@dataclass
class VixTermStructure:
    vix_9d: float | None
    vix_spot: float | None
    vix_3m: float | None
    vix_6m: float | None
    term_shape: TermShape
    contango_slope: float | None  # (vix_3m - vix_spot) / vix_spot
    backwardation_days: int        # estimated days of backwardation
    regime_cue: str


def _classify_term(vix_9d, vix_spot, vix_3m, vix_6m) -> TermShape:
    if vix_9d is None or vix_spot is None:
        return "flat"
    if vix_9d > vix_spot * 1.03:
        return "inverted_9d_spot"
    if vix_3m is None:
        return "flat"
    slope = (vix_3m - vix_spot) / vix_spot if vix_spot > 0 else 0.0
    if slope > 0.05:
        return "contango"
    if slope < -0.10:
        return "backwardation_severe"
    if slope < -0.02:
        return "backwardation_mild"
    return "flat"


def _regime_cue(term_shape: TermShape, vix_spot: float | None) -> str:
    if term_shape == "backwardation_severe":
        return "Acute fear spike — elevated crash risk; options pricing extreme stress."
    if term_shape == "backwardation_mild":
        return "Near-term uncertainty elevated — market pricing near-term risk over tail risk."
    if term_shape == "inverted_9d_spot":
        return "9-day VIX above spot — imminent event risk (FOMC, earnings, macro)."
    if term_shape == "contango":
        spot = vix_spot or 0
        if spot < 15:
            return "Deep contango + low VIX — complacency regime; watch for vol compression unwind."
        return "Normal contango — markets pricing calm near-term, standard risk environment."
    return "Flat term structure — no dominant vol regime signal."


async def fetch_vix_term_structure() -> VixTermStructure:
    """Fetch VIX term structure from Yahoo Finance."""
    try:
        import yfinance as yf
        tickers = list(VIX_TICKERS.values())
        data = yf.download(tickers, period="2d", progress=False, auto_adjust=True)["Close"]
        latest = data.iloc[-1]

        vix_9d = _safe(latest.get("^VIX9D"))
        vix_spot = _safe(latest.get("^VIX"))
        vix_3m = _safe(latest.get("^VIX3M"))
        vix_6m = _safe(latest.get("^VIX6M"))

        term_shape = _classify_term(vix_9d, vix_spot, vix_3m, vix_6m)
        slope = round((vix_3m - vix_spot) / vix_spot, 4) if vix_3m and vix_spot and vix_spot > 0 else None

        # Rough estimate: backwardation days = 0 for contango, ~5 for mild, ~15 for severe
        backwardation_days = 0
        if term_shape == "backwardation_severe":
            backwardation_days = 15
        elif term_shape == "backwardation_mild":
            backwardation_days = 5

        return VixTermStructure(
            vix_9d=vix_9d, vix_spot=vix_spot, vix_3m=vix_3m, vix_6m=vix_6m,
            term_shape=term_shape,
            contango_slope=slope,
            backwardation_days=backwardation_days,
            regime_cue=_regime_cue(term_shape, vix_spot),
        )
    except Exception as e:
        logger.warning("vix_term_fetch_failed error=%s", e)
        return VixTermStructure(
            vix_9d=None, vix_spot=None, vix_3m=None, vix_6m=None,
            term_shape="flat", contango_slope=None,
            backwardation_days=0, regime_cue="Data unavailable.",
        )


def _safe(v) -> float | None:
    try:
        f = float(v)
        import math
        return round(f, 2) if math.isfinite(f) else None
    except Exception:
        return None


def format_vix_term_for_prompt(s: VixTermStructure) -> str:
    """Format VIX term structure for inclusion in an LLM prompt."""
    return (
        f"VIX Term Structure: 9d={s.vix_9d} spot={s.vix_spot} 3m={s.vix_3m} 6m={s.vix_6m} "
        f"shape={s.term_shape} contango_slope={s.contango_slope} "
        f"backwardation_days={s.backwardation_days} regime_cue='{s.regime_cue}'"
    )
