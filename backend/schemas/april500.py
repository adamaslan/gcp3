"""April 500 adapter schema."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.tool_result import ToolResult


class April500Signals(BaseModel):
    bollinger: float | None = Field(default=None, ge=0.0, le=1.0)
    rsi: float | None = Field(default=None, ge=0.0, le=1.0)
    macd: float | None = Field(default=None, ge=0.0, le=1.0)
    ichimoku: float | None = Field(default=None, ge=0.0, le=1.0)
    volume_flow: float | None = Field(default=None, ge=0.0, le=1.0)


class April500ToolResult(ToolResult):
    net_score: float = Field(default=0.0, ge=0.0, le=1.0)
    signals: April500Signals = Field(default_factory=April500Signals)
    bar_confluence: dict[str, Any] = Field(default_factory=dict)
    support_resistance: dict[str, Any] = Field(default_factory=dict)
    multi_timeframe_outlook: dict[str, Any] = Field(default_factory=dict)
    files: list[str] = Field(default_factory=list)
    files_persisted: bool = False

