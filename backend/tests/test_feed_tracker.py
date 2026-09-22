"""Tests for feed_tracker's pure date and threshold logic."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date, datetime, timezone

from feed_tracker import expected_last_date, freshness_is_ok


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_before_settle_expects_previous_trading_day():
    assert expected_last_date(_utc(2026, 9, 22, 10)) == date(2026, 9, 21)


def test_after_settle_expects_today():
    assert expected_last_date(_utc(2026, 9, 21, 23)) == date(2026, 9, 21)


def test_standard_time_settle_boundary():
    # 22:30 UTC is 17:30 EST; a minute earlier the bar is not yet trusted.
    assert expected_last_date(_utc(2026, 12, 14, 22, 29)) == date(2026, 12, 11)
    assert expected_last_date(_utc(2026, 12, 14, 22, 30)) == date(2026, 12, 14)


def test_monday_morning_expects_friday():
    assert expected_last_date(_utc(2026, 9, 21, 10)) == date(2026, 9, 18)


def test_weekend_expects_friday():
    assert expected_last_date(_utc(2026, 9, 20, 23)) == date(2026, 9, 18)


def test_freshness_threshold():
    assert freshness_is_ok({"tracked": 54, "fresh": 49, "stale": []})
    assert not freshness_is_ok({"tracked": 54, "fresh": 48, "stale": []})
    assert not freshness_is_ok({"tracked": 0, "fresh": 0, "stale": []})


def test_quotes_threshold():
    from feed_tracker import quotes_are_ok

    assert quotes_are_ok({"data_status": {"available": 54, "expected": 54}})
    assert quotes_are_ok({"data_status": {"available": 49, "expected": 54}})
    assert not quotes_are_ok({"data_status": {"available": 40, "expected": 54}})
    assert not quotes_are_ok({})
