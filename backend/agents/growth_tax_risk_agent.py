"""Growth tax-risk agent (B2)."""
from __future__ import annotations

from config.agent_config import GrowthConfig
from firestore import write_agent_document
from schemas.growth import GrowthEvidencePacket, GrowthTaxRiskPacket


class GrowthTaxRiskAgent:
    async def run(self, evidence: GrowthEvidencePacket, config: GrowthConfig) -> GrowthTaxRiskPacket:
        tax_scores = config.tax_risk_scores
        sub_scores = {
            "tax_drag": tax_scores["long_horizon_tax_drag"] if evidence.horizon in {"2y-5y", "5y-10y", "10y-plus"} else tax_scores["short_horizon_tax_drag"],
            "horizon_fit": tax_scores["horizon_fit"],
            "turnover_risk": tax_scores["low_turnover"] if evidence.direction in {"accumulate", "hold"} else tax_scores["high_turnover"],
            "account_fit": tax_scores["account_fit"],
        }
        score = sum(sub_scores[k] * config.b2_weights[k] for k in config.b2_weights)
        packet = GrowthTaxRiskPacket(
            run_id=evidence.run_id,
            ticker=evidence.ticker,
            tax_risk_score=round(score, 4),
            key_question_answer="tax_does_not_threaten_return" if score >= tax_scores["does_not_threaten_threshold"] else "tax_threatens_return",
            sub_scores=sub_scores,
            estimated_tax_drag=round(1 - score, 4),
            supporting_evidence=["Longer holding horizon lowers modeled tax drag"],
            counter_evidence=evidence.counter_evidence,
            risk_flags=evidence.risk_flags,
        )
        write_agent_document("growth_tax_risk_packets", f"{packet.run_id}:{packet.ticker}:1", packet.model_dump(mode="json"))
        return packet
