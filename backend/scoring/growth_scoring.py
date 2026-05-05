"""Deterministic Growth quality, tax, and total scoring helpers."""
from __future__ import annotations

from typing import Any


GROWTH_SCORING_DEFAULTS: dict[str, Any] = {
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


def _section(thresholds: dict[str, Any] | None, name: str) -> dict[str, Any]:
    values = dict(GROWTH_SCORING_DEFAULTS[name])
    if thresholds and isinstance(thresholds.get(name), dict):
        values.update(thresholds[name])
    return values


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _cagr(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None and v > 0]
    if len(vals) < 2:
        return None
    years = len(vals) - 1
    return (vals[-1] / vals[0]) ** (1 / years) - 1


def score_revenue_growth(revenue_history: list[float], thresholds: dict[str, Any] | None = None) -> tuple[float, str]:
    brackets = _section(thresholds, "revenue_cagr")
    scores = _section(thresholds, "revenue_scores")
    cagr = _cagr(revenue_history[-4:])
    if cagr is None:
        return scores["insufficient"], "insufficient revenue history"
    if cagr >= brackets["excellent"]:
        return scores["excellent"], f"3-year revenue CAGR {cagr:.1%}"
    if cagr >= brackets["good"]:
        return scores["good"], f"3-year revenue CAGR {cagr:.1%}"
    if cagr >= brackets["positive"]:
        return scores["positive"], f"3-year revenue CAGR {cagr:.1%}"
    if cagr >= brackets["weak"]:
        return scores["weak"], f"low positive revenue CAGR {cagr:.1%}"
    return scores["negative"], f"negative revenue CAGR {cagr:.1%}"


def score_earnings_quality(net_income_history: list[float], fcf_history: list[float], total_assets: float | None = None, thresholds: dict[str, Any] | None = None) -> tuple[float, str]:
    brackets = _section(thresholds, "fcf_conversion")
    scores = _section(thresholds, "earnings_scores")
    pairs = [(ni, fcf) for ni, fcf in zip(net_income_history, fcf_history) if ni and ni > 0 and fcf is not None]
    if not pairs:
        return scores["insufficient"], "insufficient positive earnings history"
    conversion = sum(fcf / ni for ni, fcf in pairs) / len(pairs)
    if conversion >= brackets["excellent"]:
        return scores["excellent"], f"FCF conversion {conversion:.0%}"
    if conversion >= brackets["good"]:
        return scores["good"], f"FCF conversion {conversion:.0%}"
    if conversion >= brackets["weak"]:
        return scores["weak"], f"FCF conversion {conversion:.0%}"
    return scores["poor"], f"weak FCF conversion {conversion:.0%}"


def score_roic_trend(ebit_history: list[float], tax_rate: float, equity: float | None, debt: float | None, cash: float | None, thresholds: dict[str, Any] | None = None) -> tuple[float, str]:
    brackets = _section(thresholds, "roic")
    scores = _section(thresholds, "roic_scores")
    invested_capital = (equity or 0) + (debt or 0) - (cash or 0)
    if invested_capital <= 0 or not ebit_history:
        return scores["insufficient"], "insufficient invested-capital data"
    roic = (ebit_history[-1] * (1 - tax_rate)) / invested_capital
    if roic >= brackets["excellent"]:
        return scores["excellent"], f"ROIC {roic:.1%}"
    if roic >= brackets["good"]:
        return scores["good"], f"ROIC {roic:.1%}"
    if roic >= brackets["weak"]:
        return scores["weak"], f"ROIC {roic:.1%}"
    return scores["poor"], f"low ROIC {roic:.1%}"


def score_moat_durability(gross_margin: float | None, revenue_cagr: float | None, quarterly_revenue: list[float], rd_pct: float | None, customer_concentration: float | None, thresholds: dict[str, Any] | None = None) -> tuple[float, str]:
    cfg = _section(thresholds, "moat")
    score = cfg["base"]
    reasons = []
    if gross_margin is not None and gross_margin >= cfg["gross_margin_strong"]:
        score += cfg["gross_margin_bonus"]
        reasons.append("strong gross margin")
    if revenue_cagr is not None and revenue_cagr >= cfg["growth_good"]:
        score += cfg["growth_bonus"]
        reasons.append("durable growth")
    if len(quarterly_revenue) >= 4 and quarterly_revenue[-1] >= quarterly_revenue[-4]:
        score += cfg["quarterly_stability_bonus"]
        reasons.append("quarterly revenue stable")
    if customer_concentration is not None and customer_concentration > cfg["customer_concentration_high"]:
        score -= cfg["customer_concentration_penalty"]
        reasons.append("customer concentration risk")
    return clamp01(score), ", ".join(reasons) or "rule-based moat proxy"


def score_capital_allocation(share_count_history: list[float], capex_pct: float | None, dividend_payout: float | None, thresholds: dict[str, Any] | None = None) -> tuple[float, str]:
    cfg = _section(thresholds, "capital")
    score = cfg["base"]
    if len(share_count_history) >= 2 and share_count_history[-1] < share_count_history[0]:
        score += cfg["buyback_bonus"]
    if capex_pct is not None and capex_pct < cfg["capex_low"]:
        score += cfg["capex_bonus"]
    if dividend_payout is not None and dividend_payout > cfg["dividend_payout_high"]:
        score -= cfg["dividend_penalty"]
    return clamp01(score), "capital allocation proxy"


def score_management_alignment(insider_transactions: list[dict], ceo_ownership: float | None, sbc_pct: float | None, thresholds: dict[str, Any] | None = None) -> tuple[float, str]:
    cfg = _section(thresholds, "management")
    score = cfg["base"]
    if ceo_ownership is not None and ceo_ownership >= cfg["ceo_ownership_good"]:
        score += cfg["ownership_bonus"]
    if sbc_pct is not None and sbc_pct > cfg["sbc_high"]:
        score -= cfg["sbc_penalty"]
    return clamp01(score), "management alignment proxy"


def score_valuation_discipline(price: float | None, fcf: float | None, growth_rate: float | None, thresholds: dict[str, Any] | None = None) -> tuple[float, str]:
    cfg = _section(thresholds, "valuation")
    if fcf is not None and fcf <= 0 and growth_rate is not None and growth_rate >= cfg["pre_profit_growth"]:
        return cfg["pre_profit_score"], "valuation_exception: pre_profit_growth"
    if not price or not fcf or price <= 0:
        return cfg["insufficient"], "insufficient valuation data"
    fcf_yield = fcf / price
    if fcf_yield >= cfg["fcf_yield_excellent"]:
        return cfg["excellent_score"], f"FCF yield {fcf_yield:.1%}"
    if fcf_yield >= cfg["fcf_yield_good"]:
        return cfg["good_score"], f"FCF yield {fcf_yield:.1%}"
    return cfg["poor_score"], f"low FCF yield {fcf_yield:.1%}"


def score_balance_sheet(cash: float | None, total_debt: float | None, ebitda: float | None, interest_coverage: float | None, thresholds: dict[str, Any] | None = None) -> tuple[float, str]:
    cfg = _section(thresholds, "balance_sheet")
    cash = cash or 0
    debt = total_debt or 0
    if debt <= cash:
        return cfg["net_cash_score"], "net cash balance sheet"
    if ebitda and debt / ebitda <= cfg["leverage_good"]:
        return cfg["leverage_score"], "manageable leverage"
    if interest_coverage and interest_coverage >= cfg["interest_coverage_good"]:
        return cfg["interest_coverage_score"], "acceptable interest coverage"
    return cfg["risk_score"], "balance sheet leverage risk"


def compute_growth_quality_score(sub_scores: dict[str, float], weights: dict[str, float]) -> float:
    return clamp01(sum(sub_scores.get(name, 0.0) * weight for name, weight in weights.items()))


def compute_growth_total_score(quality_score: float, tax_score: float, risk_penalty: float, stale_penalty: float, thresholds: dict[str, Any] | None = None) -> tuple[float, dict[str, Any]]:
    caps = _section(thresholds, "penalty_caps")
    raw = 0.90 * quality_score + 0.10 * tax_score
    total_penalty = min(max(risk_penalty, 0.0) + max(stale_penalty, 0.0), caps["total_penalty"])
    total = clamp01(raw - total_penalty)
    return total, {
        "b1_growth_quality_score": quality_score,
        "b2_tax_risk_score": tax_score,
        "raw_score": round(raw, 4),
        "risk_penalty": risk_penalty,
        "stale_data_penalty": stale_penalty,
        "total_penalty": total_penalty,
        "formula": "0.90*B1 + 0.10*B2 - penalties",
    }
