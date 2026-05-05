"""Growth quality agent (B1)."""
from __future__ import annotations

from adapters.fundamentals import FundamentalsAdapter
from config.agent_config import GrowthConfig
from firestore import write_agent_document
from schemas.growth import GrowthEvidencePacket, ScoreTrajectory
from scoring.growth_scoring import (
    _cagr,
    compute_growth_quality_score,
    score_balance_sheet,
    score_capital_allocation,
    score_earnings_quality,
    score_management_alignment,
    score_moat_durability,
    score_revenue_growth,
    score_roic_trend,
    score_valuation_discipline,
)


class GrowthQualityAgent:
    def __init__(self, adapter: FundamentalsAdapter | None = None) -> None:
        self.adapter = adapter or FundamentalsAdapter()

    async def run(self, run_id: str, candidates: list[str], config: GrowthConfig) -> list[GrowthEvidencePacket]:
        out: list[GrowthEvidencePacket] = []
        for ticker in candidates[: config.growth_candidate_limit]:
            out.append(await self._analyze(run_id, ticker.strip().upper(), config))
        return out

    async def _analyze(self, run_id: str, ticker: str, config: GrowthConfig) -> GrowthEvidencePacket:
        fundamentals = await self.adapter.fetch(ticker, run_id)
        income = fundamentals.income_statements
        balances = fundamentals.balance_sheets
        cashflows = fundamentals.cash_flows
        revenue = [x.revenue for x in income if x.revenue is not None]
        net_income = [x.net_income for x in income if x.net_income is not None]
        fcf = [x.free_cash_flow for x in cashflows if x.free_cash_flow is not None]
        ebit = [x.ebit for x in income if x.ebit is not None]
        latest_income = income[-1] if income else None
        latest_balance = balances[-1] if balances else None
        revenue_cagr = _cagr(revenue[-4:]) if len(revenue) >= 2 else None
        scoring_thresholds = config.growth_scoring_thresholds

        sub_scores: dict[str, float] = {}
        evidence: list[str] = []
        hard_flags: list[str] = []
        for name, result in {
            "revenue": score_revenue_growth(revenue, scoring_thresholds),
            "earnings": score_earnings_quality(net_income, fcf, latest_balance.total_assets if latest_balance else None, scoring_thresholds),
            "roic": score_roic_trend(ebit, config.tax_rate, latest_balance.total_equity if latest_balance else None, latest_balance.total_debt if latest_balance else None, latest_balance.cash_and_equivalents if latest_balance else None, scoring_thresholds),
            "moat": score_moat_durability(
                (latest_income.gross_profit / latest_income.revenue) if latest_income and latest_income.gross_profit and latest_income.revenue else None,
                revenue_cagr,
                fundamentals.quarterly_revenue,
                None,
                None,
                scoring_thresholds,
            ),
            "capital": score_capital_allocation([x.weighted_average_shares for x in income if x.weighted_average_shares is not None], None, None, scoring_thresholds),
            "management": score_management_alignment([], None, None, scoring_thresholds),
            "valuation": score_valuation_discipline(None, fcf[-1] if fcf else None, revenue_cagr, scoring_thresholds),
            "balance_sheet": score_balance_sheet(latest_balance.cash_and_equivalents if latest_balance else None, latest_balance.total_debt if latest_balance else None, latest_income.ebitda if latest_income else None, None, scoring_thresholds),
        }.items():
            sub_scores[name] = result[0]
            evidence.append(f"{name}: {result[1]}")

        if len(revenue) >= 3 and revenue[-1] < revenue[-2] < revenue[-3]:
            hard_flags.append("revenue_declining_2_plus_years")
        if fundamentals.going_concern_doubt:
            hard_flags.append("going_concern_doubt")
        if fundamentals.insider_cluster_selling_detected:
            hard_flags.append("insider_cluster_selling")
        if not fcf or (fcf[-1] <= 0 and (revenue_cagr or 0) < config.no_clear_path_min_cagr):
            hard_flags.append("no_clear_path_to_positive_fcf")

        quality = compute_growth_quality_score(sub_scores, config.b1_weights)
        if hard_flags:
            quality = min(quality, config.hard_reject_quality_cap)
        direction = "accumulate" if quality >= config.accept_threshold and not hard_flags else "hold" if quality >= config.watchlist_threshold else "avoid"
        packet = GrowthEvidencePacket(
            run_id=run_id,
            ticker=ticker,
            direction=direction,
            horizon="2y-5y",
            growth_quality_score=round(quality, 4),
            sub_scores=sub_scores,
            score_trajectory=ScoreTrajectory(),
            tool_results=[fundamentals],
            supporting_evidence=evidence,
            counter_evidence=fundamentals.counter_evidence or ["no_material_counter_evidence_found"],
            hard_reject_flags=hard_flags,
            risk_flags=fundamentals.risk_flags,
        )
        write_agent_document("growth_evidence_packets", f"{run_id}:{ticker}:1", packet.model_dump(mode="json"))
        return packet
