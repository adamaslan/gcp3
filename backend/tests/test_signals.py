"""Tests for utils/signals.py — ai_signal() rule-based momentum classifier."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from utils.signals import ai_signal


class TestAiSignalStrongBuy:
    """pct > 3 AND position_in_range > 0.75 → strong_buy."""

    def test_clear_strong_buy(self):
        q = {"change_pct": 4.0, "price": 110, "low": 100, "high": 120}
        # position_in_range = (110-100)/(120-100) = 0.5 — NOT > 0.75, so buy not strong_buy
        # Adjust: price near top of range
        q = {"change_pct": 4.0, "price": 118, "low": 100, "high": 120}
        # position = (118-100)/20 = 0.9 > 0.75 ✓
        assert ai_signal(q) == "strong_buy"

    def test_pct_at_boundary_exactly_3_is_not_strong_buy(self):
        # pct == 3 is NOT > 3, so falls through to buy check
        q = {"change_pct": 3.0, "price": 119, "low": 100, "high": 120}
        assert ai_signal(q) == "buy"

    def test_high_pct_but_low_position_is_not_strong_buy(self):
        # pct > 3 but price near bottom of range → not strong_buy
        q = {"change_pct": 5.0, "price": 101, "low": 100, "high": 120}
        # position = 1/20 = 0.05 — falls through to buy check (pct > 1.5)
        assert ai_signal(q) == "buy"


class TestAiSignalBuy:
    """pct > 1.5 OR (pct > 0.5 AND position > 0.7) → buy."""

    def test_pct_above_1_5(self):
        q = {"change_pct": 2.0, "price": 105, "low": 100, "high": 120}
        assert ai_signal(q) == "buy"

    def test_pct_just_above_0_5_with_high_position(self):
        q = {"change_pct": 0.6, "price": 115, "low": 100, "high": 120}
        # position = 15/20 = 0.75 > 0.7 ✓
        assert ai_signal(q) == "buy"

    def test_pct_above_0_5_but_low_position_is_hold(self):
        q = {"change_pct": 0.6, "price": 102, "low": 100, "high": 120}
        # position = 2/20 = 0.1 — not > 0.7
        assert ai_signal(q) == "hold"


class TestAiSignalStrongSell:
    """pct < -3 AND position_in_range < 0.25 → strong_sell."""

    def test_clear_strong_sell(self):
        q = {"change_pct": -4.0, "price": 101, "low": 100, "high": 120}
        # position = 1/20 = 0.05 < 0.25 ✓
        assert ai_signal(q) == "strong_sell"

    def test_pct_at_neg3_boundary_is_not_strong_sell(self):
        # pct == -3 is NOT < -3
        q = {"change_pct": -3.0, "price": 101, "low": 100, "high": 120}
        assert ai_signal(q) == "sell"

    def test_big_drop_but_high_position_is_not_strong_sell(self):
        # pct < -3 but price near top of range → sell, not strong_sell
        q = {"change_pct": -5.0, "price": 118, "low": 100, "high": 120}
        # position = 18/20 = 0.9 — not < 0.25, falls through to sell (pct < -1.5)
        assert ai_signal(q) == "sell"


class TestAiSignalSell:
    """pct < -1.5 OR (pct < -0.5 AND position < 0.3) → sell."""

    def test_pct_below_neg1_5(self):
        q = {"change_pct": -2.0, "price": 110, "low": 100, "high": 120}
        assert ai_signal(q) == "sell"

    def test_pct_just_below_neg0_5_with_low_position(self):
        q = {"change_pct": -0.6, "price": 102, "low": 100, "high": 120}
        # position = 2/20 = 0.1 < 0.3 ✓
        assert ai_signal(q) == "sell"

    def test_pct_below_neg0_5_but_high_position_is_hold(self):
        q = {"change_pct": -0.6, "price": 118, "low": 100, "high": 120}
        # position = 0.9 — not < 0.3
        assert ai_signal(q) == "hold"


class TestAiSignalHold:
    """Everything else → hold."""

    def test_flat_market(self):
        q = {"change_pct": 0.0, "price": 110, "low": 100, "high": 120}
        assert ai_signal(q) == "hold"

    def test_small_positive_change_mid_range(self):
        q = {"change_pct": 0.3, "price": 110, "low": 100, "high": 120}
        assert ai_signal(q) == "hold"

    def test_small_negative_change_mid_range(self):
        q = {"change_pct": -0.3, "price": 110, "low": 100, "high": 120}
        assert ai_signal(q) == "hold"


class TestAiSignalEdgeCases:
    """Boundary conditions and missing/malformed data."""

    def test_zero_intraday_range_defaults_to_midpoint(self):
        # high == low → range = 0, position_in_range defaults to 0.5
        q = {"change_pct": 0.0, "price": 100, "low": 100, "high": 100}
        assert ai_signal(q) == "hold"

    def test_missing_price_defaults_to_zero(self):
        q = {"change_pct": 0.0}
        # price=0, low=0, high=0 → range=0 → position=0.5
        assert ai_signal(q) == "hold"

    def test_missing_change_pct_defaults_to_zero(self):
        q = {"price": 100, "low": 90, "high": 110}
        assert ai_signal(q) == "hold"

    def test_returns_string_not_none(self):
        for q in [
            {"change_pct": 10, "price": 200, "low": 100, "high": 200},
            {"change_pct": -10, "price": 100, "low": 100, "high": 200},
            {},
        ]:
            result = ai_signal(q)
            assert isinstance(result, str)
            assert result in {"strong_buy", "buy", "hold", "sell", "strong_sell"}
