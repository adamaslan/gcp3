"""Tests for TTL midnight calculation used in ai_summary, daily_blog, blog_reviewer."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timedelta, timezone
import pytest


def _calc_midnight_ttl(now: datetime) -> int:
    """Reproduce the TTL calculation from ai_summary.py and daily_blog.py."""
    tomorrow_midnight = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
    return max(1, int((tomorrow_midnight - now).total_seconds() / 3600))


class TestMidnightTTL:
    def test_just_after_midnight_has_max_ttl(self):
        # 00:01 UTC — almost 24h until next midnight
        now = datetime(2026, 4, 15, 0, 1, 0, tzinfo=timezone.utc)
        ttl = _calc_midnight_ttl(now)
        assert ttl == 23  # 23 full hours remain (int truncation)

    def test_noon_has_12h_ttl(self):
        now = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
        ttl = _calc_midnight_ttl(now)
        assert ttl == 12

    def test_one_minute_before_midnight_has_min_ttl(self):
        # 23:59 UTC — only 1 minute until midnight → max(1, 0) = 1
        now = datetime(2026, 4, 15, 23, 59, 0, tzinfo=timezone.utc)
        ttl = _calc_midnight_ttl(now)
        assert ttl == 1

    def test_midnight_exactly_has_24h_ttl(self):
        # Exactly 00:00 UTC — tomorrow midnight is 24h away
        now = datetime(2026, 4, 15, 0, 0, 0, tzinfo=timezone.utc)
        ttl = _calc_midnight_ttl(now)
        assert ttl == 24

    def test_ttl_never_below_one(self):
        # Even in edge cases, TTL is at least 1h to avoid immediate expiry
        now = datetime(2026, 4, 15, 23, 59, 59, tzinfo=timezone.utc)
        ttl = _calc_midnight_ttl(now)
        assert ttl >= 1

    def test_ttl_never_exceeds_24(self):
        # Should never be more than 24h (that would mean we passed midnight)
        for hour in range(24):
            now = datetime(2026, 4, 15, hour, 0, 0, tzinfo=timezone.utc)
            ttl = _calc_midnight_ttl(now)
            assert ttl <= 24, f"TTL={ttl} at hour={hour} exceeds 24"

    def test_ttl_is_always_positive(self):
        for hour in range(24):
            now = datetime(2026, 4, 15, hour, 30, 0, tzinfo=timezone.utc)
            ttl = _calc_midnight_ttl(now)
            assert ttl > 0, f"TTL={ttl} at hour={hour} is not positive"

    def test_year_boundary_dec31_to_jan1(self):
        # Dec 31 → Jan 1 year rollover
        now = datetime(2026, 12, 31, 18, 0, 0, tzinfo=timezone.utc)
        ttl = _calc_midnight_ttl(now)
        assert ttl == 6

    def test_month_boundary(self):
        # Last day of month → first day of next month
        now = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)
        ttl = _calc_midnight_ttl(now)
        assert ttl == 12
