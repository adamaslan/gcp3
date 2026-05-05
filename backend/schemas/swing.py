"""Pydantic contracts for the Swing research agent."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from schemas.tool_result import ToolResult


Direction = Literal["long", "short", "neutral", "avoid"]
Horizon = Literal["intraday", "2d-5d", "1w-3w", "1m-2m"]
Verdict = Literal["pass", "watch", "mutate", "reject", "needs_review"]
Decision = Literal["accept", "watchlist", "reject", "needs_review"]


def enforce_research_label(value: str) -> str:
    if value != "research_only":
        raise ValueError("compliance_label must be research_only")
    return value


class SwingEvidencePacket(BaseModel):
    run_id: str
    ticker: str
    iteration_number: int = Field(default=1, ge=1)
    direction: Direction = "neutral"
    horizon: Horizon = "1w-3w"
    swing_discovery_score: float = Field(ge=0.0, le=1.0)
    feature_scores: dict[str, float] = Field(default_factory=dict)
    tool_results: list[ToolResult] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    is_stale: bool = False
    llm_summary: str | None = None
    ai_degraded: bool = False
    compliance_label: str = "research_only"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("feature_scores")
    @classmethod
    def feature_scores_are_normalized(cls, value: dict[str, float]) -> dict[str, float]:
        for name, score in value.items():
            if score < 0.0 or score > 1.0:
                raise ValueError(f"feature score {name} must be in [0,1]")
        return value

    @field_validator("compliance_label")
    @classmethod
    def validate_compliance_label(cls, value: str) -> str:
        return enforce_research_label(value)


class SwingCritiquePacket(BaseModel):
    run_id: str
    ticker: str
    iteration_number: int = Field(default=1, ge=1)
    swing_critic_score: float = Field(ge=0.0, le=1.0)
    verdict: Verdict
    entry_zone: dict[str, float] = Field(default_factory=dict)
    invalidation_level: float | None = None
    reward_risk_estimate: float | None = None
    risk_penalty: float = Field(default=0.0, ge=0.0, le=0.35)
    stale_data_penalty: float = Field(default=0.0, ge=0.0, le=0.30)
    hard_blockers: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    llm_summary: str | None = None
    ai_degraded: bool = False
    compliance_label: str = "research_only"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("compliance_label")
    @classmethod
    def validate_compliance_label(cls, value: str) -> str:
        return enforce_research_label(value)


class FinalSwingDecision(BaseModel):
    run_id: str
    ticker: str
    decision: Decision
    direction: Direction
    horizon: Horizon
    total_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    decision_reason: str
    supporting_evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    compliance_label: str = "research_only"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("compliance_label")
    @classmethod
    def validate_compliance_label(cls, value: str) -> str:
        return enforce_research_label(value)


class SwingIteration(BaseModel):
    run_id: str
    ticker: str
    iteration_number: int = Field(ge=1)
    evidence: SwingEvidencePacket
    critique: SwingCritiquePacket
    total_score: float = Field(ge=0.0, le=1.0)
    mutation_plan: dict[str, Any] | None = None
    stopped: bool = False
    stop_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SwingCandidateState(BaseModel):
    run_id: str
    ticker: str
    latest_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Decision | Literal["running"] = "running"
    iteration_count: int = 0
    mutations_tried: list[str] = Field(default_factory=list)
    score_history: list[float] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SwingRun(BaseModel):
    run_id: str
    mode: Literal["premarket", "intraday", "postmarket", "manual"] = "manual"
    status: Literal["running", "completed", "failed", "partial"] = "running"
    candidates: list[str] = Field(default_factory=list)
    decisions: list[FinalSwingDecision] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    compliance_label: str = "research_only"

    @field_validator("compliance_label")
    @classmethod
    def validate_compliance_label(cls, value: str) -> str:
        return enforce_research_label(value)

