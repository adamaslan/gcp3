"""Pydantic contracts for the Growth research agent."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from schemas.swing import enforce_research_label
from schemas.tool_result import ToolResult


GrowthDirection = Literal["accumulate", "hold", "trim", "avoid"]
GrowthHorizon = Literal["2m-6m", "6m-2y", "2y-5y", "5y-10y", "10y-plus"]
KeyQuestionAnswer = Literal["tax_does_not_threaten_return", "tax_threatens_return", "tax_destroys_return"]
GrowthDecision = Literal["accept", "watchlist", "reject", "needs_review"]


class ScoreTrajectory(BaseModel):
    trend_direction: Literal["improving", "flat", "deteriorating", "insufficient_history"] = "insufficient_history"
    prior_scores: list[float] = Field(default_factory=list)
    score_trend: float = 0.0


class GrowthEvidencePacket(BaseModel):
    run_id: str
    ticker: str
    iteration_number: int = Field(default=1, ge=1)
    direction: GrowthDirection = "hold"
    horizon: GrowthHorizon = "2y-5y"
    growth_quality_score: float = Field(ge=0.0, le=1.0)
    sub_scores: dict[str, float] = Field(default_factory=dict)
    score_trajectory: ScoreTrajectory = Field(default_factory=ScoreTrajectory)
    tool_results: list[ToolResult] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    hard_reject_flags: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    compliance_label: str = "research_only"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("sub_scores")
    @classmethod
    def sub_scores_are_normalized(cls, value: dict[str, float]) -> dict[str, float]:
        for name, score in value.items():
            if score < 0.0 or score > 1.0:
                raise ValueError(f"sub-score {name} must be in [0,1]")
        return value

    @field_validator("compliance_label")
    @classmethod
    def validate_compliance_label(cls, value: str) -> str:
        return enforce_research_label(value)


class GrowthTaxRiskPacket(BaseModel):
    run_id: str
    ticker: str
    iteration_number: int = Field(default=1, ge=1)
    tax_risk_score: float = Field(ge=0.0, le=1.0)
    key_question_answer: KeyQuestionAnswer
    sub_scores: dict[str, float] = Field(default_factory=dict)
    estimated_tax_drag: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_penalty: float = Field(default=0.0, ge=0.0, le=0.35)
    stale_data_penalty: float = Field(default=0.0, ge=0.0, le=0.30)
    supporting_evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    compliance_label: str = "research_only"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("compliance_label")
    @classmethod
    def validate_compliance_label(cls, value: str) -> str:
        return enforce_research_label(value)


class FinalGrowthDecision(BaseModel):
    run_id: str
    ticker: str
    decision: GrowthDecision
    direction: GrowthDirection
    horizon: GrowthHorizon
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


class GrowthIteration(BaseModel):
    run_id: str
    ticker: str
    iteration_number: int = Field(ge=1)
    evidence: GrowthEvidencePacket
    tax_risk: GrowthTaxRiskPacket
    total_score: float = Field(ge=0.0, le=1.0)
    stopped: bool = False
    stop_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GrowthCandidateState(BaseModel):
    run_id: str
    ticker: str
    latest_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: GrowthDecision | Literal["running"] = "running"
    iteration_count: int = 0
    score_history: list[float] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GrowthRun(BaseModel):
    run_id: str
    status: Literal["running", "completed", "failed", "partial"] = "running"
    candidates: list[str] = Field(default_factory=list)
    decisions: list[FinalGrowthDecision] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    compliance_label: str = "research_only"

    @field_validator("compliance_label")
    @classmethod
    def validate_compliance_label(cls, value: str) -> str:
        return enforce_research_label(value)

