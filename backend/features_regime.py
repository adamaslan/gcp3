"""Feature #16 — Regime Transition Probability (Rule-based HMM Phase 1).

5-state regime classifier using logistic blend of macro feature z-scores:
  risk_on | risk_off | transitional | flight_to_quality | euphoria

Phase 2: swap for true Gaussian HMM (hmmlearn) behind the same interface.
Data inputs: VIX, yield spread, SPY return, breadth, put/call ratio.
"""
import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

logger = logging.getLogger(__name__)

RegimeName = Literal["risk_on", "risk_off", "transitional", "flight_to_quality", "euphoria"]

REGIME_NAMES: list[str] = ["risk_on", "risk_off", "transitional", "flight_to_quality", "euphoria"]


@dataclass
class RegimeProbability:
    as_of_date: str
    regime_probs: dict[str, float]
    dominant_regime: str
    dominant_confidence: float
    days_in_current_regime: int
    transition_probability_24h: float
    transition_target: str | None
    model_version: str
    evidence_features: list[str] = field(default_factory=list)


def _softmax(logits: list[float]) -> list[float]:
    e = [np.exp(x - max(logits)) for x in logits]
    total = sum(e)
    return [v / total for v in e]


def compute_regime(
    vix_spot: float,
    vix_3m: float,
    yield_10y_2y_spread: float,
    spy_return_5d: float,
    breadth_pct: float,
    put_call_ratio: float,
    as_of_date: str,
    days_in_current: int = 0,
) -> RegimeProbability:
    """Rule-based 5-state regime classifier.

    Args:
        vix_spot: Current VIX level.
        vix_3m: 3-month VIX futures.
        yield_10y_2y_spread: 10Y - 2Y Treasury spread in percentage points.
        spy_return_5d: SPY 5-day return.
        breadth_pct: Fraction of S&P 500 stocks above 50d MA.
        put_call_ratio: Equity put/call ratio.
        as_of_date: ISO date string.
        days_in_current: Days in the current dominant regime.

    Returns:
        RegimeProbability with all 5 regime probabilities.
    """
    # Feature z-scores using approximate historical norms
    vix_z = (vix_spot - 20) / 8.0
    spy_z = spy_return_5d / 0.02
    breadth_z = (breadth_pct - 0.55) / 0.15
    pc_z = (put_call_ratio - 0.85) / 0.20
    spread_z = (yield_10y_2y_spread - 0.5) / 0.8

    # Logits for each regime based on feature combinations
    # risk_on: low vix, strong spy, high breadth, low pc
    logit_risk_on = -vix_z * 1.2 + spy_z * 1.5 + breadth_z * 1.0 - pc_z * 0.5

    # risk_off: high vix, weak spy, low breadth, high pc
    logit_risk_off = vix_z * 1.5 - spy_z * 1.5 - breadth_z * 1.0 + pc_z * 0.5

    # transitional: moderate vix, flat spy, mixed breadth
    logit_transitional = -abs(vix_z) * 0.5 - abs(spy_z) * 0.5 - abs(breadth_z) * 0.5 + 0.5

    # flight_to_quality: high vix, inverted yield curve, bond-led
    logit_ftq = vix_z * 0.8 - spread_z * 1.5 - spy_z * 1.0 + pc_z * 0.3

    # euphoria: very low vix, strong spy, high breadth, low pc
    logit_euphoria = -vix_z * 2.0 + spy_z * 1.0 + breadth_z * 1.5 - pc_z * 1.0 - 1.5

    logits = [logit_risk_on, logit_risk_off, logit_transitional, logit_ftq, logit_euphoria]
    probs = _softmax(logits)
    prob_dict = dict(zip(REGIME_NAMES, probs))

    dominant = max(prob_dict, key=lambda k: prob_dict[k])
    dominant_conf = prob_dict[dominant]

    # Transition probability: high when dominant confidence is low or falling
    transition_prob = max(0.0, min(1.0, 1.0 - dominant_conf + 0.05 * (days_in_current / 30)))
    next_regime = sorted(prob_dict, key=lambda k: prob_dict[k], reverse=True)[1]

    evidence = ["vix_term_structure", "spy_momentum", "breadth_momentum", "yield_curve", "put_call"]

    return RegimeProbability(
        as_of_date=as_of_date,
        regime_probs={k: round(v, 3) for k, v in prob_dict.items()},
        dominant_regime=dominant,
        dominant_confidence=round(dominant_conf, 3),
        days_in_current_regime=days_in_current,
        transition_probability_24h=round(transition_prob, 3),
        transition_target=next_regime if transition_prob > 0.25 else None,
        model_version="regime_rule_v1",
        evidence_features=evidence,
    )


def format_regime_for_prompt(r: RegimeProbability) -> str:
    probs_str = ", ".join(f"{k}:{v:.2f}" for k, v in r.regime_probs.items())
    drivers = ", ".join(r.evidence_features[:3])
    return (
        f"<regime>\n"
        f"  probs={{{probs_str}}}\n"
        f"  dominant={r.dominant_regime}({r.dominant_confidence:.2f}) "
        f"days_in={r.days_in_current_regime} "
        f"transition_24h={r.transition_probability_24h:.2f} "
        f"next_likely={r.transition_target or 'none'}\n"
        f"  drivers=[{drivers}]\n"
        f"</regime>"
    )


def validate_regime(r: RegimeProbability) -> list[str]:
    errors: list[str] = []
    total = sum(r.regime_probs.values())
    if abs(total - 1.0) > 0.01:
        errors.append(f"regime_probs sum to {total:.3f}, must be 1.0 ± 0.01")
    for k, v in r.regime_probs.items():
        if not (0 <= v <= 1):
            errors.append(f"regime_probs[{k}]={v} outside [0,1]")
    return errors
