"""Growth orchestrator joining B1 quality and B2 tax risk."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agents.growth_quality_agent import GrowthQualityAgent
from agents.growth_tax_risk_agent import GrowthTaxRiskAgent
from config.agent_config import GrowthConfig, load_growth_config
from firestore import read_agent_document, write_agent_document
from schemas.growth import FinalGrowthDecision, GrowthCandidateState, GrowthIteration, GrowthRun
from scoring.growth_scoring import compute_growth_total_score


class GrowthOrchestrator:
    def __init__(self, config: GrowthConfig | None = None) -> None:
        self.config = config or load_growth_config()
        self.quality = GrowthQualityAgent()
        self.tax = GrowthTaxRiskAgent()

    async def run(self, candidates: list[str], run_id: str | None = None) -> GrowthRun:
        run_id = run_id or f"growth-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
        tickers = [t.strip().upper() for t in candidates if t.strip()][: self.config.growth_candidate_limit]
        run = GrowthRun(run_id=run_id, status="running", candidates=tickers)
        write_agent_document("growth_runs", run_id, run.model_dump(mode="json"))
        decisions: list[FinalGrowthDecision] = []
        for evidence in await self.quality.run(run_id, tickers, self.config):
            tax = await self.tax.run(evidence, self.config)
            total, breakdown = compute_growth_total_score(evidence.growth_quality_score, tax.tax_risk_score, tax.risk_penalty, tax.stale_data_penalty)
            decision, reason = self._decide(total, bool(evidence.hard_reject_flags))
            final = FinalGrowthDecision(
                run_id=run_id,
                ticker=evidence.ticker,
                decision=decision,
                direction=evidence.direction if decision != "reject" else "avoid",
                horizon=evidence.horizon,
                total_score=total,
                score_breakdown=breakdown,
                decision_reason=reason,
                supporting_evidence=evidence.supporting_evidence + tax.supporting_evidence,
                counter_evidence=evidence.counter_evidence,
                risk_flags=sorted(set(evidence.risk_flags + tax.risk_flags + evidence.hard_reject_flags)),
            )
            iteration = GrowthIteration(run_id=run_id, ticker=evidence.ticker, iteration_number=1, evidence=evidence, tax_risk=tax, total_score=total, stopped=True, stop_reason=reason)
            state = GrowthCandidateState(run_id=run_id, ticker=evidence.ticker, latest_score=total, status=decision, iteration_count=1, score_history=[total], risk_flags=final.risk_flags)
            write_agent_document("growth_iterations", f"{run_id}:{evidence.ticker}:1", iteration.model_dump(mode="json"))
            write_agent_document("growth_candidates", f"{run_id}:{evidence.ticker}", state.model_dump(mode="json"))
            write_agent_document("final_growth_decisions", f"{run_id}:{evidence.ticker}", final.model_dump(mode="json"))
            decisions.append(final)
        run.status = "completed"
        run.decisions = decisions
        run.completed_at = datetime.now(timezone.utc)
        write_agent_document("growth_runs", run_id, run.model_dump(mode="json"))
        return run

    def _decide(self, total: float, hard_reject: bool) -> tuple[str, str]:
        if hard_reject:
            return "reject", "Growth hard-rejection flag overrode numeric score"
        if total >= self.config.accept_threshold:
            return "accept", "Score met growth accept threshold"
        if total >= self.config.watchlist_threshold:
            return "watchlist", "Score met growth watchlist threshold"
        if total < self.config.reject_threshold:
            return "reject", "Score fell below growth reject threshold"
        return "needs_review", "Growth score requires review"


def get_growth_run(run_id: str) -> dict | None:
    return read_agent_document("growth_runs", run_id)
