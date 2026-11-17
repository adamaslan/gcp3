"""No fabricated actionable prices from a normalized discovery score."""
import asyncio
import pytest
from agents.swing_critic_agent import SwingCriticAgent
from agents.swing_orchestrator import SwingOrchestrator
from config.agent_config import SwingConfig
from schemas.swing import SwingEvidencePacket


@pytest.mark.parametrize('direction', ['long', 'short', 'neutral'])
@pytest.mark.parametrize('score', [0.1, 0.5, 0.99])
def test_missing_verified_prices_never_become_entry_or_risk_reward(monkeypatch, direction, score):
    writes = []
    monkeypatch.setattr('agents.swing_critic_agent.write_agent_document', lambda *args: writes.append(args))
    evidence = SwingEvidencePacket(run_id='synthetic-run', ticker='TEST', direction=direction, swing_discovery_score=score)
    result = asyncio.run(SwingCriticAgent().run(evidence, SwingConfig()))
    assert result.entry_zone == {} and result.invalidation_level is None and result.reward_risk_estimate is None
    assert result.verdict == 'needs_review'
    assert 'verified_price_context_missing' in result.risk_flags
    assert result.swing_critic_score <= score  # no fake 2:1 reward/risk uplift
    persisted = writes[0][2]
    assert persisted['reward_risk_estimate'] is None and persisted['entry_zone'] == {}
    assert 'manual review required' in persisted['supporting_evidence'][0]
    assert SwingOrchestrator()._decide(.99, result.verdict)[0] == 'needs_review'


def test_staleness_still_preserved_without_synthetic_risk_reward(monkeypatch):
    monkeypatch.setattr('agents.swing_critic_agent.write_agent_document', lambda *args: None)
    evidence = SwingEvidencePacket(run_id='r', ticker='TEST', direction='long', swing_discovery_score=.9, is_stale=True)
    result = asyncio.run(SwingCriticAgent().run(evidence, SwingConfig()))
    assert result.stale_data_penalty == .2 and 'stale_data' in result.risk_flags
    assert result.swing_critic_score == .7 and result.verdict == 'needs_review'
