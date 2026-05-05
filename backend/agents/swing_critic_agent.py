"""Rule-based Swing critic agent (A2)."""
from __future__ import annotations

from config.agent_config import SwingConfig
from firestore import write_agent_document
from schemas.swing import SwingCritiquePacket, SwingEvidencePacket


class SwingCriticAgent:
    async def run(self, evidence_packet: SwingEvidencePacket, config: SwingConfig) -> SwingCritiquePacket:
        blockers: list[str] = []
        risk_flags = list(evidence_packet.risk_flags)
        risk_penalty = 0.0
        stale_penalty = 0.0

        if evidence_packet.is_stale:
            stale_penalty = 0.20
            risk_flags.append("stale_data")
        if evidence_packet.swing_discovery_score < config.reject_threshold:
            risk_penalty += 0.10
        if "feature_unavailable" in evidence_packet.risk_flags:
            risk_penalty += 0.05

        direction = evidence_packet.direction
        base = evidence_packet.swing_discovery_score
        if direction == "neutral":
            base -= 0.08
            risk_flags.append("unclear_direction")

        entry_zone = {"low": round(base * 100, 2), "high": round((base * 100) + 1.5, 2)}
        invalidation_level = round(entry_zone["low"] * 0.97, 2) if direction == "long" else round(entry_zone["high"] * 1.03, 2)
        reward_risk = 2.0 if base >= 0.65 else 1.2 if base >= 0.50 else 0.8
        if reward_risk < 1.0:
            blockers.append("reward_risk_below_floor")

        score = max(0.0, min(1.0, base - risk_penalty - stale_penalty + (0.05 if reward_risk >= 2 else 0)))
        if blockers:
            verdict = "reject"
        elif evidence_packet.is_stale:
            verdict = "needs_review"
        elif score >= config.accept_threshold:
            verdict = "pass"
        elif score >= config.watchlist_threshold:
            verdict = "watch"
        elif score >= config.reject_threshold:
            verdict = "mutate"
        else:
            verdict = "reject"

        packet = SwingCritiquePacket(
            run_id=evidence_packet.run_id,
            ticker=evidence_packet.ticker,
            iteration_number=evidence_packet.iteration_number,
            swing_critic_score=round(score, 4),
            verdict=verdict,
            entry_zone=entry_zone,
            invalidation_level=invalidation_level,
            reward_risk_estimate=reward_risk,
            risk_penalty=min(risk_penalty, 0.35),
            stale_data_penalty=min(stale_penalty, 0.30),
            hard_blockers=blockers,
            supporting_evidence=[f"Rule critique verdict {verdict}", f"Reward/risk estimate {reward_risk:.1f}"],
            counter_evidence=evidence_packet.counter_evidence,
            risk_flags=sorted(set(risk_flags)),
            ai_degraded=True,
        )
        write_agent_document(
            "swing_critique_packets",
            f"{packet.run_id}:{packet.ticker}:{packet.iteration_number}",
            packet.model_dump(mode="json"),
        )
        return packet

