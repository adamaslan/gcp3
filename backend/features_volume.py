"""Feature #12 — Volume Z-Score.

Converts raw volume into regime-aware surprise:
  z = (today_vol - 20d_avg) / 20d_std

Also classifies the joint price/volume signal (bullish confirm, etc.).
Data source: yfinance OHLCV (volume already in daily bar fetch, zero extra cost).
"""
import logging
from dataclasses import dataclass
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class VolumeZScore:
    timeframe: str
    lookback_days: int
    today_volume: int
    mean_volume: float
    stddev_volume: float
    z_score: float
    percentile_rank: float
    relative_to_adv: float
    classification: Literal[
        "extreme_accumulation",
        "heavy_accumulation",
        "elevated",
        "normal",
        "quiet",
        "drought",
    ]
    price_volume_confirm: Literal[
        "bullish_confirm",
        "bearish_confirm",
        "bullish_nonconfirm",
        "bearish_nonconfirm",
        "neutral",
    ]


def _classify_volume(z: float) -> str:
    if z > 3:
        return "extreme_accumulation"
    if z > 2:
        return "heavy_accumulation"
    if z > 1:
        return "elevated"
    if z >= -1:
        return "normal"
    if z >= -2:
        return "quiet"
    return "drought"


def _classify_price_volume(today_return: float, z: float) -> str:
    up = today_return > 0
    heavy = z > 1
    if up and heavy:
        return "bullish_confirm"
    if not up and heavy:
        return "bearish_confirm"
    if up and not heavy:
        return "bullish_nonconfirm"
    if not up and not heavy:
        return "bearish_nonconfirm"
    return "neutral"


def compute_volume_zscore(
    bars: pd.DataFrame,
    timeframe: str = "1D",
    lookback: int = 20,
) -> VolumeZScore | None:
    """Compute volume z-score and price/volume confirmation signal.

    Args:
        bars: DataFrame with 'volume' and 'close' columns (oldest first).
        timeframe: Timeframe label.
        lookback: Rolling window for mean/std (default 20).

    Returns:
        VolumeZScore or None if insufficient bars.
    """
    # Filter out half-sessions (< 390 min trading) if session_minutes present
    if "session_minutes" in bars.columns:
        bars = bars[bars["session_minutes"] >= 390]

    if len(bars) < lookback + 1:
        logger.warning("volume_z: insufficient bars (need %d, got %d)", lookback + 1, len(bars))
        return None

    hist = bars["volume"].iloc[-(lookback + 1):-1]
    today_vol = int(bars["volume"].iloc[-1])
    mean = float(hist.mean())
    std = float(hist.std(ddof=0))
    z = (today_vol - mean) / std if std > 0 else 0.0
    pct_rank = float((hist < today_vol).sum() / lookback)
    adv = mean if mean > 0 else 1.0

    today_return = 0.0
    if len(bars) >= 2 and bars["close"].iloc[-2] > 0:
        today_return = (bars["close"].iloc[-1] - bars["close"].iloc[-2]) / bars["close"].iloc[-2]

    return VolumeZScore(
        timeframe=timeframe,
        lookback_days=lookback,
        today_volume=today_vol,
        mean_volume=round(mean, 0),
        stddev_volume=round(std, 0),
        z_score=round(z, 3),
        percentile_rank=round(pct_rank, 3),
        relative_to_adv=round(today_vol / adv, 3),
        classification=_classify_volume(z),  # type: ignore[arg-type]
        price_volume_confirm=_classify_price_volume(today_return, z),  # type: ignore[arg-type]
    )


def format_volume_for_prompt(vz: VolumeZScore) -> str:
    return (
        f"<volume>z={vz.z_score:.1f} pct={round(vz.percentile_rank * 100)} "
        f"classification={vz.classification} confirm={vz.price_volume_confirm}</volume>"
    )


def validate_volume_zscore(vz: VolumeZScore) -> list[str]:
    errors: list[str] = []
    if vz.today_volume < 0:
        errors.append(f"today_volume={vz.today_volume} is negative")
    if not (0 <= vz.percentile_rank <= 1):
        errors.append(f"percentile_rank={vz.percentile_rank} outside [0,1]")
    return errors
