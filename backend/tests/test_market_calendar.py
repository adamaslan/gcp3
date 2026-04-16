"""Tests for market_calendar.py — highest-risk module (hardcoded holiday data)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date
import pytest
from market_calendar import is_trading_day, trading_date


class TestIsTradingDay:
    # ── Weekends ──────────────────────────────────────────────────────────────
    def test_saturday_is_not_trading_day(self):
        assert is_trading_day(date(2026, 4, 18)) is False

    def test_sunday_is_not_trading_day(self):
        assert is_trading_day(date(2026, 4, 19)) is False

    # ── Regular weekdays ──────────────────────────────────────────────────────
    def test_regular_monday_is_trading_day(self):
        assert is_trading_day(date(2026, 4, 13)) is True

    def test_regular_friday_is_trading_day(self):
        assert is_trading_day(date(2026, 4, 17)) is True

    # ── 2026 holidays ─────────────────────────────────────────────────────────
    def test_2026_new_years_day(self):
        assert is_trading_day(date(2026, 1, 1)) is False

    def test_2026_mlk_day(self):
        assert is_trading_day(date(2026, 1, 19)) is False

    def test_2026_presidents_day(self):
        assert is_trading_day(date(2026, 2, 16)) is False

    def test_2026_good_friday(self):
        assert is_trading_day(date(2026, 4, 3)) is False

    def test_2026_memorial_day(self):
        assert is_trading_day(date(2026, 5, 25)) is False

    def test_2026_independence_day_observed(self):
        # July 3 observed (July 4 falls on Saturday in 2026)
        assert is_trading_day(date(2026, 7, 3)) is False

    def test_2026_labor_day(self):
        assert is_trading_day(date(2026, 9, 7)) is False

    def test_2026_thanksgiving(self):
        assert is_trading_day(date(2026, 11, 26)) is False

    def test_2026_christmas(self):
        assert is_trading_day(date(2026, 12, 25)) is False

    # Day before/after holiday is a trading day
    def test_day_before_christmas_2026_is_trading_day(self):
        assert is_trading_day(date(2026, 12, 24)) is True

    def test_day_after_christmas_2026_is_trading_day(self):
        # Dec 26 is a Saturday in 2026, so Dec 28 (Monday) should be trading
        assert is_trading_day(date(2026, 12, 28)) is True

    # ── 2027 holidays ─────────────────────────────────────────────────────────
    def test_2027_new_years_day(self):
        assert is_trading_day(date(2027, 1, 1)) is False

    def test_2027_good_friday(self):
        assert is_trading_day(date(2027, 3, 26)) is False

    def test_2027_christmas(self):
        assert is_trading_day(date(2027, 12, 25)) is False

    # ── 2028 holidays ─────────────────────────────────────────────────────────
    def test_2028_good_friday(self):
        assert is_trading_day(date(2028, 4, 14)) is False

    def test_2028_independence_day(self):
        assert is_trading_day(date(2028, 7, 4)) is False

    def test_2028_christmas(self):
        assert is_trading_day(date(2028, 12, 25)) is False

    # ── Out-of-range year emits warning but doesn't crash ─────────────────────
    def test_out_of_range_year_does_not_raise(self):
        # 2025 is before our supported range — should warn but not crash
        result = is_trading_day(date(2025, 7, 4))
        assert isinstance(result, bool)

    def test_out_of_range_year_2025_july4_returns_true(self):
        # July 4, 2025 is a Friday and a US holiday, but our holiday set only
        # covers 2026-2028. So is_trading_day() returns True (incorrectly) for
        # out-of-range years. This test documents that known gap — the warning
        # log message is the only signal. To fix: add 2025 holidays or migrate
        # to pandas_market_calendars.
        assert is_trading_day(date(2025, 7, 4)) is True  # known gap: 2025 not in holiday set

    # ── Boundary: supported years all covered ─────────────────────────────────
    @pytest.mark.parametrize("d,expected", [
        (date(2026, 1, 2), True),   # First trading day of 2026
        (date(2027, 1, 4), True),   # First trading day of 2027 (Jan 1 is holiday, Jan 2-3 are weekend)
        (date(2028, 1, 3), True),   # First trading day of 2028
    ])
    def test_first_trading_day_of_year(self, d, expected):
        assert is_trading_day(d) == expected
