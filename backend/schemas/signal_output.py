"""Canonical Pydantic schemas for signal outputs (Section A, Weakness #4/#7)."""
from __future__ import annotations

import math
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SignalDirection(str, Enum):
    strong_buy = "strong_buy"
    buy = "buy"
    hold = "hold"
    sell = "sell"
    strong_sell = "strong_sell"


class Timeframe(str, Enum):
    one_day = "1D"
    five_day = "5D"
    one_month = "1M"
    three_month = "3M"
    six_month = "6M"
    one_year = "1Y"


class EvidenceSource(str, Enum):
    technical = "technical"
    fundamental = "fundamental"
    macro = "macro"
    news_sentiment = "news_sentiment"
    options_flow = "options_flow"
    sector_relative = "sector_relative"
    cross_asset = "cross_asset"
    earnings = "earnings"
    rule_based = "rule_based"


class EvidenceItem(BaseModel):
    source: EvidenceSource
    weight: float = Field(ge=0.0, le=1.0)
    summary: str
    is_counter: bool = False

    @field_validator("weight")
    @classmethod
    def weight_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("weight must be finite")
        return round(v, 4)


class Evidence(BaseModel):
    items: list[EvidenceItem]

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "Evidence":
        supporting = [e for e in self.items if not e.is_counter]
        total = sum(e.weight for e in supporting)
        if supporting and abs(total - 1.0) > 0.01:
            raise ValueError(f"Supporting evidence weights must sum to 1.0 ± 0.01, got {total:.4f}")
        return self

    @model_validator(mode="after")
    def counter_argument_present_if_high_confidence(self) -> "Evidence":
        # Checked at SignalOutput level where confidence is available
        return self


class Signal(BaseModel):
    direction: SignalDirection
    confidence: float = Field(gt=0.0, lt=1.0, description="Must not be 0 or 1 exactly")
    timeframe: Timeframe
    evidence: Evidence
    ai_degraded: bool = False
    prompt_version: str = "unknown"

    @field_validator("confidence")
    @classmethod
    def confidence_not_extreme(cls, v: float) -> float:
        if v == 0.0 or v == 1.0:
            raise ValueError("confidence must be strictly between 0 and 1")
        return round(v, 4)

    @model_validator(mode="after")
    def hold_confidence_cap(self) -> "Signal":
        if self.direction == SignalDirection.hold and self.confidence > 0.75:
            raise ValueError("hold signals must have confidence ≤ 0.75")
        return self

    @model_validator(mode="after")
    def high_confidence_requires_counter(self) -> "Signal":
        if self.confidence > 0.6:
            has_counter = any(e.is_counter for e in self.evidence.items)
            if not has_counter:
                raise ValueError("confidence > 0.6 requires at least one counter_argument evidence item")
        return self


class DivergencePattern(str, Enum):
    aligned_bullish = "aligned_bullish"
    aligned_bearish = "aligned_bearish"
    short_bull_long_bear = "short_bull_long_bear"
    short_bear_long_bull = "short_bear_long_bull"
    mixed = "mixed"
    insufficient_data = "insufficient_data"


class TimeframeMatrix(BaseModel):
    ticker: str
    signals: dict[str, Signal]  # Timeframe value -> Signal
    alignment_score: float = Field(ge=0.0, le=1.0)
    divergence_pattern: DivergencePattern
    divergence_interpretation: str = ""
    computed_at: str = ""

    @model_validator(mode="after")
    def alignment_finite(self) -> "TimeframeMatrix":
        if not math.isfinite(self.alignment_score):
            raise ValueError("alignment_score must be finite")
        return self


class SignalOutput(BaseModel):
    """Top-level response schema for all 7 nav endpoints."""
    ticker: str
    signal: Signal
    matrix: TimeframeMatrix | None = None
    feature_unavailable: list[str] = Field(default_factory=list)
    schema_version: str = "1.0"


def alignment_score(signals: list[Signal]) -> float:
    """Compute alignment score: fraction of signals agreeing with majority direction."""
    if not signals:
        return 0.0
    directions = [s.direction for s in signals]
    majority = max(set(directions), key=directions.count)
    agreeing = sum(1 for d in directions if d == majority)
    return round(agreeing / len(directions), 4)


def classify_divergence(signals: dict[str, Signal]) -> DivergencePattern:
    """Classify divergence pattern from timeframe signals."""
    short_tfs = {Timeframe.one_day.value, Timeframe.five_day.value}
    long_tfs = {Timeframe.one_month.value, Timeframe.three_month.value,
                Timeframe.six_month.value, Timeframe.one_year.value}

    bull = {SignalDirection.buy, SignalDirection.strong_buy}
    bear = {SignalDirection.sell, SignalDirection.strong_sell}

    short_signals = [s for tf, s in signals.items() if tf in short_tfs]
    long_signals = [s for tf, s in signals.items() if tf in long_tfs]

    if not short_signals or not long_signals:
        return DivergencePattern.insufficient_data

    short_bull = sum(1 for s in short_signals if s.direction in bull)
    short_bear = sum(1 for s in short_signals if s.direction in bear)
    long_bull = sum(1 for s in long_signals if s.direction in bull)
    long_bear = sum(1 for s in long_signals if s.direction in bear)

    short_bias = "bull" if short_bull > short_bear else ("bear" if short_bear > short_bull else "neutral")
    long_bias = "bull" if long_bull > long_bear else ("bear" if long_bear > long_bull else "neutral")

    if short_bias == "bull" and long_bias == "bull":
        return DivergencePattern.aligned_bullish
    if short_bias == "bear" and long_bias == "bear":
        return DivergencePattern.aligned_bearish
    if short_bias == "bull" and long_bias == "bear":
        return DivergencePattern.short_bull_long_bear
    if short_bias == "bear" and long_bias == "bull":
        return DivergencePattern.short_bear_long_bull
    return DivergencePattern.mixed
