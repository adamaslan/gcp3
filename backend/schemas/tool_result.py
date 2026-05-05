"""Shared tool-result contract for Swing + Growth agents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ToolFamily = Literal[
    "market_data",
    "technical",
    "fundamental",
    "tax",
    "risk",
    "llm",
    "rag",
    "storage",
    "compliance",
]
ToolStatus = Literal["ok", "partial", "failed", "stale", "skipped"]


class ToolResult(BaseModel):
    tool_name: str
    tool_family: ToolFamily
    inputs_hash: str
    timeframe: str | None = None
    status: ToolStatus = "ok"
    score_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    source_timestamps: dict[str, datetime | str | None] = Field(default_factory=dict)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("inputs_hash")
    @classmethod
    def inputs_hash_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("inputs_hash is required")
        return value

