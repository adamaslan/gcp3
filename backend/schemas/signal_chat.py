"""Chat contracts for the per-ticker signal-explain agent (interactivity Axis 2)."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SignalChatRequest(BaseModel):
    question: str = Field(min_length=1)


class SignalChatResponse(BaseModel):
    ticker: str
    answer: str
    tool_calls: int = 0
    fallback_used: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
