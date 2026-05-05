"""Swing orchestrator joining A1 discovery and A2 critique."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agents.swing_critic_agent import SwingCriticAgent
from agents.swing_discovery_agent import SwingDiscoveryAgent
from config.agent_config import SwingConfig, load_swing_config
from firestore import read_agent_document, write_agent_document
from scoring.swing_scoring import compute_swing_total_score
from schemas.swing import FinalSwingDecision, SwingCandidateState, SwingIteration, SwingRun


MUTATIONS = [
    "timeframe_expand",
    "timeframe_contract",
    "sector_relative_check",
    "risk_filter_tighten",
    "volatility_regime_adjust",
    "deep_scan_extra_period",
    "counter_evidence_expand",
]


class SwingOrchestrator:
    def __init__(self, config: SwingConfig | None = None) -> None:
        self.config = config or load_swing_config()
        self.discovery = SwingDiscoveryAgent()
        self.critic = SwingCriticAgent()

    async def run(self, candidates: list[str], mode: str = "manual", run_id: str | None = None) -> SwingRun:
        run_id = run_id or f"swing-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
        tickers = [t.strip().upper() for t in candidates if t.strip()]
        run = SwingRun(run_id=run_id, mode=mode, status="running", candidates=tickers)
        write_agent_document("swing_runs", run_id, run.model_dump(mode="json"))

        evidence_packets = await self.discovery.run(run_id, tickers, self.config)
        decisions: list[FinalSwingDecision] = []
        for evidence in evidence_packets:
            critique = await self.critic.run(evidence, self.config)
            total, breakdown = compute_swing_total_score(evidence, critique, self.config)
            decision, reason = self._decide(total, critique.verdict)
            final = FinalSwingDecision(
                run_id=run_id,
                ticker=evidence.ticker,
                decision=decision,
                direction=evidence.direction if decision != "reject" else "avoid",
                horizon=evidence.horizon,
                total_score=total,
                score_breakdown=breakdown,
                decision_reason=reason,
                supporting_evidence=evidence.supporting_evidence + critique.supporting_evidence,
                counter_evidence=evidence.counter_evidence,
                risk_flags=sorted(set(evidence.risk_flags + critique.risk_flags + critique.hard_blockers)),
            )
            iteration = SwingIteration(
                run_id=run_id,
                ticker=evidence.ticker,
                iteration_number=1,
                evidence=evidence,
                critique=critique,
                total_score=total,
                mutation_plan=None if decision != "needs_review" else {"type": "counter_evidence_expand"},
                stopped=True,
                stop_reason=reason,
            )
            state = SwingCandidateState(
                run_id=run_id,
                ticker=evidence.ticker,
                latest_score=total,
                status=decision,
                iteration_count=1,
                mutations_tried=[],
                score_history=[total],
                risk_flags=final.risk_flags,
            )
            write_agent_document("swing_iterations", f"{run_id}:{evidence.ticker}:1", iteration.model_dump(mode="json"))
            write_agent_document("swing_candidates", f"{run_id}:{evidence.ticker}", state.model_dump(mode="json"))
            write_agent_document("final_swing_decisions", f"{run_id}:{evidence.ticker}", final.model_dump(mode="json"))
            decisions.append(final)

        run.status = "completed"
        run.decisions = decisions
        run.completed_at = datetime.now(timezone.utc)
        write_agent_document("swing_runs", run_id, run.model_dump(mode="json"))
        return run

    def _decide(self, total: float, verdict: str) -> tuple[str, str]:
        if verdict == "reject":
            return "reject", "Hard blocker or low-quality critique rejected the candidate"
        if verdict == "needs_review":
            return "needs_review", "Required data was stale or incomplete"
        if total >= self.config.accept_threshold and verdict == "pass":
            return "accept", "Score met accept threshold and critique passed"
        if total >= self.config.watchlist_threshold:
            return "watchlist", "Score met watchlist threshold"
        if total < self.config.reject_threshold:
            return "reject", "Score fell below reject threshold"
        return "needs_review", "Score remained between reject and watchlist thresholds"


def get_swing_run(run_id: str) -> dict | None:
    return read_agent_document("swing_runs", run_id)

