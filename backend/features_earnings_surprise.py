"""Feature #23 — Earnings Surprise & PEAD (Post-Earnings Announcement Drift).

Data: Finnhub earnings calendar + actuals (free tier). Alpha Vantage fallback.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"
ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

BeatCategory = Literal["large_beat", "beat", "in_line", "miss", "large_miss"]
GuidanceChange = Literal["raised", "maintained", "lowered", "no_guidance"]


@dataclass
class EarningsSurprise:
    ticker: str
    eps_surprise_pct: float | None
    eps_surprise_zscore: float | None
    beat_category: BeatCategory
    guidance_change: GuidanceChange
    pead_window: int               # days remaining in PEAD window (default 60)
    reaction_vs_surprise: float | None  # post-earnings day-1 return minus expected given beat
    days_to_next_report: int | None


def _beat_category(surprise_pct: float | None) -> BeatCategory:
    if surprise_pct is None:
        return "in_line"
    if surprise_pct > 10:
        return "large_beat"
    if surprise_pct > 2:
        return "beat"
    if surprise_pct < -10:
        return "large_miss"
    if surprise_pct < -2:
        return "miss"
    return "in_line"


async def _finnhub_earnings(
    ticker: str, client: httpx.AsyncClient
) -> tuple[float | None, float | None, int | None]:
    """Fetch most-recent EPS actual/estimate and next earnings date.

    Returns:
        (eps_surprise_pct, days_to_next_report, last_eps_actual)
    """
    api_key = os.getenv("FINNHUB_API_KEY", "")
    today = date.today()
    from_date = (today - timedelta(days=90)).isoformat()
    to_date = today.isoformat()
    try:
        resp = await client.get(
            f"{FINNHUB_BASE}/stock/earnings",
            params={"symbol": ticker, "token": api_key},
            timeout=8,
        )
        resp.raise_for_status()
        items = resp.json()
        if not items:
            return None, None, None
        latest = items[0]
        actual = latest.get("actual")
        estimate = latest.get("estimate")
        if actual is not None and estimate is not None and estimate != 0:
            surprise_pct = round((actual - estimate) / abs(estimate) * 100, 4)
        else:
            surprise_pct = None
    except Exception as e:
        logger.warning("finnhub_earnings_failed ticker=%s error=%s", ticker, e)
        surprise_pct = None

    # Next earnings date
    days_to_next = None
    try:
        cal_resp = await client.get(
            f"{FINNHUB_BASE}/calendar/earnings",
            params={"symbol": ticker, "token": api_key, "from": today.isoformat(),
                    "to": (today + timedelta(days=90)).isoformat()},
            timeout=8,
        )
        cal_data = cal_resp.json().get("earningsCalendar", [])
        if cal_data:
            next_date = date.fromisoformat(cal_data[0].get("date", today.isoformat()))
            days_to_next = (next_date - today).days
    except Exception as e:
        logger.warning("finnhub_earnings_calendar_failed ticker=%s error=%s", ticker, e)

    return surprise_pct, days_to_next, None


async def fetch_earnings_surprise(ticker: str) -> EarningsSurprise:
    """Fetch earnings surprise and PEAD metrics for a ticker.

    Args:
        ticker: Stock symbol.

    Returns:
        EarningsSurprise dataclass.
    """
    async with httpx.AsyncClient() as client:
        surprise_pct, days_to_next, _ = await _finnhub_earnings(ticker, client)

        if surprise_pct is None:
            # Alpha Vantage fallback
            try:
                av_key = os.getenv("ALPHA_VANTAGE_KEY", "demo")
                resp = await client.get(
                    ALPHA_VANTAGE_BASE,
                    params={"function": "EARNINGS", "symbol": ticker, "apikey": av_key},
                    timeout=10,
                )
                quarterly = resp.json().get("quarterlyEarnings", [])
                if quarterly:
                    q = quarterly[0]
                    actual = float(q.get("reportedEPS", 0) or 0)
                    estimate = float(q.get("estimatedEPS", 0) or 0)
                    if estimate != 0:
                        surprise_pct = round((actual - estimate) / abs(estimate) * 100, 4)
            except Exception as e:
                logger.warning("alpha_vantage_earnings_failed ticker=%s error=%s", ticker, e)

    beat_cat = _beat_category(surprise_pct)

    # PEAD window: 60-day drift window from most recent earnings date
    # Without exact earnings date we default to 30 days remaining
    pead_window = 30

    return EarningsSurprise(
        ticker=ticker,
        eps_surprise_pct=surprise_pct,
        eps_surprise_zscore=None,  # requires historical distribution — populated by feature_store
        beat_category=beat_cat,
        guidance_change="no_guidance",  # Finnhub free tier doesn't provide guidance text
        pead_window=pead_window,
        reaction_vs_surprise=None,
        days_to_next_report=days_to_next,
    )


def format_earnings_for_prompt(s: EarningsSurprise) -> str:
    """Format earnings surprise for inclusion in an LLM prompt."""
    return (
        f"Earnings ({s.ticker}): surprise={s.eps_surprise_pct}% "
        f"zscore={s.eps_surprise_zscore} beat={s.beat_category} "
        f"guidance={s.guidance_change} pead_window={s.pead_window}d "
        f"days_to_next={s.days_to_next_report}"
    )
