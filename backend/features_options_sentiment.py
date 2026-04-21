"""Feature #20 — Put/Call Ratio & Options Sentiment.

Fetches CBOE equity + index P/C ratios (free), computes EMAs and z-scores.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

CBOE_EQUITY_PC_URL = "https://www.cboe.com/us/options/market_statistics/daily/"
CBOE_CSV_URL = "https://www.cboe.com/publish/scheduledtask/mktstat/pcall/total_pc_ratio.csv"

Classification = Literal["extreme_fear", "fear", "neutral", "greed", "extreme_greed"]


@dataclass
class OptionsSentiment:
    equity_pc_ratio: float | None
    index_pc_ratio: float | None
    total_pc_ratio: float | None
    ema_5d: float | None
    ema_21d: float | None
    zscore_6m: float | None
    classification: Classification
    contrarian_signal: Literal["buy", "sell", "neutral"]
    vix_put_call_divergence: bool


def _classify(zscore: float | None) -> Classification:
    if zscore is None:
        return "neutral"
    if zscore < -1.5:
        return "extreme_greed"
    if zscore < -0.5:
        return "greed"
    if zscore > 1.5:
        return "extreme_fear"
    if zscore > 0.5:
        return "fear"
    return "neutral"


def _contrarian(classification: Classification) -> Literal["buy", "sell", "neutral"]:
    if classification in ("extreme_fear", "fear"):
        return "buy"
    if classification in ("extreme_greed", "greed"):
        return "sell"
    return "neutral"


async def fetch_options_sentiment(vix_level: float | None = None) -> OptionsSentiment:
    """Fetch CBOE P/C ratios and compute options sentiment features.

    Args:
        vix_level: Current VIX spot level for divergence check (optional).

    Returns:
        OptionsSentiment dataclass.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(CBOE_CSV_URL, follow_redirects=True)
            resp.raise_for_status()
            from io import StringIO
            df = pd.read_csv(StringIO(resp.text), skiprows=2, header=0)
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
            # CBOE CSV has DATE, P/C Ratio columns
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                df = df.dropna(subset=["date"]).sort_values("date")

            pc_col = next((c for c in df.columns if "ratio" in c or "put" in c), None)
            if pc_col is None or len(df) < 5:
                raise ValueError("Could not parse CBOE P/C CSV")

            series = df[pc_col].astype(float).dropna()
            current = float(series.iloc[-1])
            ema5 = float(series.ewm(span=5).mean().iloc[-1])
            ema21 = float(series.ewm(span=21).mean().iloc[-1])

            window_6m = series.tail(126)
            mean_6m = float(window_6m.mean())
            std_6m = float(window_6m.std())
            zscore = (current - mean_6m) / std_6m if std_6m > 0 else 0.0

            classification = _classify(zscore)
            contrarian = _contrarian(classification)

            # VIX divergence: high VIX + low P/C = unusual (equity hedgers absent despite fear)
            vix_pc_divergence = False
            if vix_level is not None and vix_level > 25 and classification in ("greed", "extreme_greed"):
                vix_pc_divergence = True

            return OptionsSentiment(
                equity_pc_ratio=current,
                index_pc_ratio=None,  # would need separate CBOE index P/C endpoint
                total_pc_ratio=current,
                ema_5d=round(ema5, 4),
                ema_21d=round(ema21, 4),
                zscore_6m=round(zscore, 4),
                classification=classification,
                contrarian_signal=contrarian,
                vix_put_call_divergence=vix_pc_divergence,
            )

    except Exception as e:
        logger.warning("options_sentiment_fetch_failed error=%s", e)
        return OptionsSentiment(
            equity_pc_ratio=None, index_pc_ratio=None, total_pc_ratio=None,
            ema_5d=None, ema_21d=None, zscore_6m=None,
            classification="neutral", contrarian_signal="neutral",
            vix_put_call_divergence=False,
        )


def format_options_for_prompt(s: OptionsSentiment) -> str:
    """Format options sentiment for inclusion in an LLM prompt."""
    return (
        f"Options Sentiment (P/C Ratio): total={s.total_pc_ratio} "
        f"ema5={s.ema_5d} ema21={s.ema_21d} zscore_6m={s.zscore_6m} "
        f"classification={s.classification} contrarian={s.contrarian_signal} "
        f"vix_pc_divergence={s.vix_put_call_divergence}"
    )
