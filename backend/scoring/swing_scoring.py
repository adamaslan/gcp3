"""Explainable Swing score aggregation."""
from __future__ import annotations

from typing import Any

from schemas.swing import SwingCritiquePacket, SwingEvidencePacket


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def compute_swing_total_score(
    evidence: SwingEvidencePacket,
    critique: SwingCritiquePacket,
    config: Any,
) -> tuple[float, dict]:
    risk_cap = getattr(config, "penalty_caps", {}).get("risk_penalty", 0.35)
    stale_cap = getattr(config, "penalty_caps", {}).get("stale_data_penalty", 0.30)
    total_cap = getattr(config, "penalty_caps", {}).get("total_penalty", 0.55)
    risk_penalty = min(float(critique.risk_penalty), risk_cap)
    stale_penalty = min(float(critique.stale_data_penalty), stale_cap)
    total_penalty = min(risk_penalty + stale_penalty, total_cap)
    a1_weight = getattr(config, "a1_weight", 0.50)
    a2_weight = getattr(config, "a2_weight", 0.50)
    raw = a1_weight * evidence.swing_discovery_score + a2_weight * critique.swing_critic_score
    total = clamp01(raw - total_penalty)
    return total, {
        "a1_swing_discovery_score": evidence.swing_discovery_score,
        "a2_swing_critic_score": critique.swing_critic_score,
        "raw_score": round(raw, 4),
        "risk_penalty": risk_penalty,
        "stale_data_penalty": stale_penalty,
        "total_penalty": total_penalty,
        "formula": f"{a1_weight:.2f}*A1 + {a2_weight:.2f}*A2 - penalties",
    }
