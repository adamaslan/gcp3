import pytest

from compliance.research_only import sanitize_response_text
from config.agent_config import GrowthConfig, load_growth_config, load_swing_config
from schemas.growth import GrowthEvidencePacket
from schemas.swing import SwingEvidencePacket
from schemas.fundamentals import CashFlowSnapshot, FundamentalsToolResult
from agents.growth_quality_agent import GrowthQualityAgent
from scoring.growth_scoring import compute_growth_total_score
from scoring.swing_scoring import compute_swing_total_score
from schemas.swing import SwingCritiquePacket


def test_research_only_label_rejects_other_values():
    with pytest.raises(ValueError):
        SwingEvidencePacket(run_id="r", ticker="AAPL", swing_discovery_score=0.5, compliance_label="execution")


def test_configs_load_and_growth_weights_sum():
    swing = load_swing_config()
    growth = load_growth_config()
    assert swing.accept_threshold == 0.78
    assert round(sum(growth.b1_weights.values()), 6) == 1.0
    assert round(sum(growth.b2_weights.values()), 6) == 1.0


def test_growth_weight_validator_catches_bad_sum():
    data = load_growth_config().model_dump()
    data["b1_weights"]["revenue"] = 0.99
    with pytest.raises(ValueError):
        GrowthConfig.model_validate(data)


def test_swing_score_breakdown_is_explainable():
    evidence = SwingEvidencePacket(run_id="r", ticker="AAPL", swing_discovery_score=0.8)
    critique = SwingCritiquePacket(run_id="r", ticker="AAPL", swing_critic_score=0.7, verdict="pass", risk_penalty=0.1)
    score, breakdown = compute_swing_total_score(evidence, critique, load_swing_config())
    assert score == 0.65
    assert breakdown["formula"] == "0.50*A1 + 0.50*A2 - penalties"


def test_growth_total_score_formula():
    score, breakdown = compute_growth_total_score(0.8, 0.7, 0.05, 0.0)
    assert score == pytest.approx(0.74)
    assert breakdown["formula"] == "0.90*B1 + 0.10*B2 - penalties"


def test_research_only_sanitizer_flags_execution_language():
    text, violated = sanitize_response_text("please place order now")
    assert violated is True
    assert "place order" not in text


@pytest.mark.asyncio
async def test_growth_quality_flags_no_clear_path_with_empty_revenue_and_negative_fcf(monkeypatch):
    monkeypatch.setattr("agents.growth_quality_agent.write_agent_document", lambda *args, **kwargs: None)

    class Adapter:
        async def fetch(self, ticker, run_id):
            return FundamentalsToolResult(
                tool_name="fundamentals",
                tool_family="fundamental",
                inputs_hash="fixture",
                cash_flows=[CashFlowSnapshot(fiscal_year=2025, free_cash_flow=-1.0)],
            )

    packets = await GrowthQualityAgent(adapter=Adapter()).run("r", ["AAPL"], load_growth_config())
    assert "no_clear_path_to_positive_fcf" in packets[0].hard_reject_flags
