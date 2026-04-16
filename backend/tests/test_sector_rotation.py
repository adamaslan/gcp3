"""Tests for sector_rotation._momentum_score() — financial calculation correctness."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from sector_rotation import _momentum_score, _rule_based_rotation_analysis


class TestMomentumScore:
    def test_positive_change_at_high_scores_highest(self):
        # Price at the high, strong positive day → maximum positive momentum
        q = {"change_pct": 2.0, "price": 100.0, "high": 100.0, "low": 95.0}
        score = _momentum_score(q)
        assert score > 0

    def test_negative_change_at_low_scores_most_negative(self):
        # Price at the low, strong negative day → maximum negative momentum
        q = {"change_pct": -2.0, "price": 95.0, "high": 100.0, "low": 95.0}
        score = _momentum_score(q)
        assert score < 0

    def test_flat_day_scores_near_zero(self):
        q = {"change_pct": 0.0, "price": 100.0, "high": 102.0, "low": 98.0}
        score = _momentum_score(q)
        assert score == 0.0

    def test_zero_range_defaults_to_midpoint(self):
        # high == low (circuit breaker scenario) — should not divide by zero
        q = {"change_pct": 1.5, "price": 100.0, "high": 100.0, "low": 100.0}
        score = _momentum_score(q)
        # pos defaults to 0.5, so score = 0.6 * 1.5 + 0.4 * (0.5*2-1)*abs(1.5) = 0.9 + 0 = 0.9
        assert score == pytest.approx(0.9, abs=0.001)

    def test_formula_is_60_40_weighted(self):
        # change_pct=1.0, price at midpoint (pos=0.5)
        # Expected: 0.6*1.0 + 0.4*(0.5*2-1)*abs(1.0) = 0.6 + 0 = 0.6
        q = {"change_pct": 1.0, "price": 100.0, "high": 105.0, "low": 95.0}
        score = _momentum_score(q)
        assert score == pytest.approx(0.6, abs=0.001)

    def test_price_at_top_of_range_amplifies_positive(self):
        # change_pct=1.0, price at top (pos=1.0)
        # pos=1.0, score = 0.6*1.0 + 0.4*(1.0*2-1)*1.0 = 0.6 + 0.4 = 1.0
        q = {"change_pct": 1.0, "price": 105.0, "high": 105.0, "low": 95.0}
        score = _momentum_score(q)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_price_at_bottom_of_range_dampens_positive(self):
        # change_pct=1.0, price at bottom (pos=0.0)
        # pos=0.0, score = 0.6*1.0 + 0.4*(0.0*2-1)*1.0 = 0.6 - 0.4 = 0.2
        q = {"change_pct": 1.0, "price": 95.0, "high": 105.0, "low": 95.0}
        score = _momentum_score(q)
        assert score == pytest.approx(0.2, abs=0.001)

    def test_missing_keys_default_to_zero(self):
        # Empty dict — all defaults should prevent KeyError
        score = _momentum_score({})
        assert isinstance(score, float)

    def test_result_is_rounded_to_3_decimals(self):
        q = {"change_pct": 1.23456, "price": 100.0, "high": 110.0, "low": 90.0}
        score = _momentum_score(q)
        assert score == round(score, 3)


class TestRuleBasedRotationAnalysis:
    def _make_ranked(self, sectors: list[str], scores: list[float]) -> list[dict]:
        return [{"sector": s, "momentum_score": sc} for s, sc in zip(sectors, scores)]

    def test_empty_input_returns_string(self):
        result = _rule_based_rotation_analysis([])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_offensive_regime_detected(self):
        ranked = self._make_ranked(
            ["Technology", "Financials", "Consumer Discretionary", "Utilities", "Real Estate"],
            [1.5, 1.2, 0.8, -0.5, -1.0],
        )
        result = _rule_based_rotation_analysis(ranked)
        assert "offensive" in result

    def test_defensive_regime_detected(self):
        ranked = self._make_ranked(
            ["Utilities", "Consumer Staples", "Healthcare", "Technology", "Energy"],
            [1.5, 1.2, 0.8, -0.5, -1.0],
        )
        result = _rule_based_rotation_analysis(ranked)
        assert "defensive" in result

    def test_leaders_and_laggards_in_output(self):
        ranked = self._make_ranked(
            ["Technology", "Financials", "Energy", "Utilities", "Real Estate"],
            [2.0, 1.5, 0.5, -0.5, -1.5],
        )
        result = _rule_based_rotation_analysis(ranked)
        assert "Technology" in result
        assert "Real Estate" in result

    def test_wide_spread_signals_conviction(self):
        ranked = self._make_ranked(
            ["Technology", "Financials", "Utilities"],
            [3.0, 0.0, -3.0],
        )
        result = _rule_based_rotation_analysis(ranked)
        assert "conviction" in result

    def test_narrow_spread_signals_indecision(self):
        ranked = self._make_ranked(
            ["Technology", "Financials", "Utilities"],
            [0.5, 0.0, -0.5],
        )
        result = _rule_based_rotation_analysis(ranked)
        assert "indecision" in result
