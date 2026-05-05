"""RAG chat contracts for run-scoped research Q&A."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class RagChatRequest(BaseModel):
    run_id: str
    question: str = Field(min_length=1)
    ticker: str | None = None
    system: Literal["swing", "growth"]
    max_chunks: int = Field(default=6, ge=1, le=12)


class RagCitation(BaseModel):
    source_id: str
    collection: str
    ticker: str | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagChatResponse(BaseModel):
    run_id: str
    answer: str
    citations: list[RagCitation] = Field(default_factory=list)
    sanitized: bool = False
    compliance_label: str = "research_only"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChromaChunkMetadata(BaseModel):
    run_id: str
    ticker: str | None = None
    collection: str
    document_id: str
    chunk_index: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

