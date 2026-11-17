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

        # Discovery emits normalized scores, not a verified entry price, stop,
        # target, spread or transaction cost. Multiplying a score by 100 cannot
        # manufacture these inputs or a measured reward/risk ratio.
        risk_flags.extend(["verified_price_context_missing", "reward_risk_unavailable"])
        score = max(0.0, min(1.0, base - risk_penalty - stale_penalty))
        verdict = "needs_review"

        packet = SwingCritiquePacket(
            run_id=evidence_packet.run_id,
            ticker=evidence_packet.ticker,
            iteration_number=evidence_packet.iteration_number,
            swing_critic_score=round(score, 4),
            verdict=verdict,
            entry_zone={},
            invalidation_level=None,
            reward_risk_estimate=None,
            risk_penalty=min(risk_penalty, 0.35),
            stale_data_penalty=min(stale_penalty, 0.30),
            hard_blockers=blockers,
            supporting_evidence=["Rule-only critique: no verified entry, invalidation or reward/risk inputs; manual review required"],
            counter_evidence=evidence_packet.counter_evidence + ["Discovery confidence is not a price or a reward/risk measurement"],
            risk_flags=sorted(set(risk_flags)),
            ai_degraded=True,
        )
        write_agent_document(
            "swing_critique_packets",
            f"{packet.run_id}:{packet.ticker}:{packet.iteration_number}",
            packet.model_dump(mode="json"),
        )
        return packet
