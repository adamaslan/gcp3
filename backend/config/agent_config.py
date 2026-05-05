"""Config loaders for Swing + Growth agent settings."""
from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - used in minimal local environments
    yaml = None

logger = logging.getLogger(__name__)

DEFAULT_LLM_PROVIDER_ORDER = ["openrouter_qwen3", "mistral", "gemini"]

DEFAULT_GROWTH_SCORING_THRESHOLDS: dict[str, Any] = {
    "revenue_cagr": {"excellent": 0.20, "good": 0.10, "positive": 0.03, "weak": 0.00},
    "revenue_scores": {"excellent": 1.0, "good": 0.80, "positive": 0.55, "weak": 0.35, "negative": 0.05, "insufficient": 0.35},
    "fcf_conversion": {"excellent": 0.90, "good": 0.70, "weak": 0.40},
    "earnings_scores": {"excellent": 1.0, "good": 0.80, "weak": 0.55, "poor": 0.20, "insufficient": 0.30},
    "roic": {"excellent": 0.20, "good": 0.12, "weak": 0.06},
    "roic_scores": {"excellent": 1.0, "good": 0.80, "weak": 0.50, "poor": 0.20, "insufficient": 0.35},
    "moat": {"base": 0.45, "gross_margin_strong": 0.55, "gross_margin_bonus": 0.20, "growth_good": 0.10, "growth_bonus": 0.15, "quarterly_stability_bonus": 0.10, "customer_concentration_high": 0.30, "customer_concentration_penalty": 0.20},
    "capital": {"base": 0.55, "buyback_bonus": 0.20, "capex_low": 0.20, "capex_bonus": 0.10, "dividend_payout_high": 0.80, "dividend_penalty": 0.20},
    "management": {"base": 0.55, "ceo_ownership_good": 0.01, "ownership_bonus": 0.20, "sbc_high": 0.10, "sbc_penalty": 0.25},
    "valuation": {"pre_profit_growth": 0.30, "pre_profit_score": 0.55, "insufficient": 0.40, "fcf_yield_excellent": 0.06, "fcf_yield_good": 0.03, "excellent_score": 0.90, "good_score": 0.65, "poor_score": 0.30},
    "balance_sheet": {"net_cash_score": 0.95, "leverage_good": 2.0, "leverage_score": 0.75, "interest_coverage_good": 4.0, "interest_coverage_score": 0.60, "risk_score": 0.25},
    "penalty_caps": {"total_penalty": 0.55},
}

DEFAULT_TAX_RISK_SCORES: dict[str, Any] = {
    "long_horizon_tax_drag": 0.75,
    "short_horizon_tax_drag": 0.55,
    "horizon_fit": 0.80,
    "low_turnover": 0.75,
    "high_turnover": 0.45,
    "account_fit": 0.65,
    "does_not_threaten_threshold": 0.65,
}


class SwingConfig(BaseModel):
    accept_threshold: float = 0.78
    watchlist_threshold: float = 0.62
    reject_threshold: float = 0.45
    max_iterations_per_candidate: int = 5
    april500_finalist_limit: int = 5
    max_april500_timeframes_per_candidate: int = 3
    min_average_dollar_volume: float = 20_000_000
    max_spread_bps: float = 50
    run_mode_ttls: dict[str, int] = Field(default_factory=dict)
    penalty_caps: dict[str, float] = Field(default_factory=dict)
    feature_weights: dict[str, float] = Field(default_factory=dict)
    requires_counter_evidence: bool = True
    a1_weight: float = 0.50
    a2_weight: float = 0.50
    april500_script_path: str | None = None
    llm_provider_order: list[str] = Field(default_factory=lambda: list(DEFAULT_LLM_PROVIDER_ORDER))
    llm_timeout_seconds: int = 45

    @model_validator(mode="after")
    def validate_swing_weight_sum(self) -> "SwingConfig":
        if round(self.a1_weight + self.a2_weight, 6) != 1.0:
            raise ValueError("a1_weight and a2_weight must sum to 1.00")
        return self


class GrowthConfig(BaseModel):
    accept_threshold: float = 0.75
    watchlist_threshold: float = 0.60
    reject_threshold: float = 0.45
    max_iterations_per_candidate: int = 4
    growth_candidate_limit: int = 20
    growth_finalist_limit: int = 5
    min_history_years: int = 5
    min_average_dollar_volume: float = 50_000_000
    b1_weights: dict[str, float]
    b2_weights: dict[str, float]
    calibration_brackets: dict[str, Any] = Field(default_factory=dict)
    growth_scoring_thresholds: dict[str, Any] = Field(default_factory=lambda: deepcopy(DEFAULT_GROWTH_SCORING_THRESHOLDS))
    tax_rate: float = 0.21
    tax_risk_scores: dict[str, Any] = Field(default_factory=lambda: deepcopy(DEFAULT_TAX_RISK_SCORES))
    no_clear_path_min_cagr: float = 0.20
    hard_reject_quality_cap: float = 0.44
    llm_provider_order: list[str] = Field(default_factory=lambda: list(DEFAULT_LLM_PROVIDER_ORDER))
    llm_timeout_seconds: int = 45
    financial_ttl_seconds: int = 604800
    weekly_run_cron: str = "0 18 * * 0"

    @model_validator(mode="after")
    def validate_weight_sums(self) -> "GrowthConfig":
        for label, weights in (("b1_weights", self.b1_weights), ("b2_weights", self.b2_weights)):
            if round(sum(weights.values()), 6) != 1.0:
                raise ValueError(f"{label} must sum to 1.00")
        return self


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        text = fh.read()
    if yaml is not None:
        return yaml.safe_load(text) or {}
    logger.warning("PyYAML unavailable; using limited fallback YAML parser for %s", path)
    return _parse_simple_yaml(text)


def _parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the simple key/value + one-level mapping configs used here."""
    root: dict[str, Any] = {}
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" "):
            key, _, value = raw_line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                root[key] = _parse_scalar(value)
                current = None
            else:
                root[key] = {}
                current = root[key]
            continue
        if current is not None:
            key, _, value = raw_line.strip().partition(":")
            current[key.strip()] = _parse_scalar(value)
    return root


def load_swing_config(path: str | Path | None = None) -> SwingConfig:
    cfg_path = Path(path) if path else Path(__file__).with_name("swing_config.yaml")
    return SwingConfig.model_validate(_load_yaml(cfg_path))


def load_growth_config(path: str | Path | None = None) -> GrowthConfig:
    cfg_path = Path(path) if path else Path(__file__).with_name("growth_config.yaml")
    return GrowthConfig.model_validate(_load_yaml(cfg_path))
