"""Offline history validation. No DB or provider calls."""
from unittest.mock import patch
from datetime import datetime, timezone
import pandas as pd
import pytest
import etf_store


def frame(dates, closes):
    return pd.DataFrame({'adjusted_close': closes}, index=pd.to_datetime(dates))


def compute(df):
    with patch.object(etf_store, 'load_history', return_value=df), patch.object(etf_store, 'datetime', wraps=datetime) as clock:
        clock.now.return_value = datetime(2026, 11, 11, 17, tzinfo=timezone.utc)
        try:
            return etf_store.compute_returns('TEST')
        except etf_store.InvalidHistory:
            return None


def test_positive_control():
    r = compute(frame(['2026-11-10', '2026-11-09', '2026-10-09', '2025-11-10', '2025-12-31'], [110, 100, 100, 80, 90]))
    assert r['1d'] == 10
    assert r['1m'] == 10
    assert r['1y'] == 37.5
    assert r['ytd'] == 22.22


@pytest.mark.parametrize('bad', [-10, 0, float('inf'), float('-inf')])
def test_invalid_price_withholds_history(bad):
    assert compute(frame(['2026-11-10', '2026-11-09'], [110, bad])) is None


def test_zero_prior_year_withholds_not_infinite():
    assert compute(frame(['2026-11-10', '2026-11-09', '2025-12-31'], [110, 100, 0])) is None


def test_stale_short_period_baseline_is_not_one_day_return():
    r = compute(frame(['2026-11-10', '2026-09-01'], [110, 100]))
    assert r['1d'] is None
    assert r['1m'] is None


def test_same_date_different_price_withholds_history():
    assert compute(frame(['2026-11-10', '2026-11-09', '2026-11-09'], [110, 100, 80])) is None


def test_identical_duplicate_dates_do_not_change_result():
    r = compute(frame(['2026-11-09', '2026-11-10', '2026-11-09'], [100, 110, 100]))
    assert r['1d'] == 10


def test_future_history_is_withheld():
    assert compute(frame(['2099-11-10', '2099-11-09'], [110, 100])) is None


def test_holiday_gap_uses_previous_session_not_arbitrary_old_price():
    r = compute(frame(['2026-11-09', '2026-11-06'], [110, 100]))
    assert r['1d'] == 10


def test_stale_latest_history_is_withheld():
    assert compute(frame(['2025-11-10', '2025-11-07'], [110, 100])) is None


def test_finite_prices_cannot_emit_infinite_percentage():
    r = compute(frame(['2026-11-10', '2026-11-09'], [1e308, 1e-308]))
    assert r['1d'] is None


@pytest.mark.parametrize('bad', [float('nan'), 'bad'])
def test_nonnumeric_price_withholds_history(bad):
    assert compute(frame(['2026-11-10', '2026-11-09'], [110, bad])) is None


def test_invalid_is_distinct_from_missing_history():
    with patch.object(etf_store, 'load_history', return_value=frame(['2026-11-10', '2026-11-09'], [110, -1])):
        with pytest.raises(etf_store.InvalidHistory):
            etf_store.compute_returns('TEST')
    with patch.object(etf_store, 'load_history', return_value=None):
        assert etf_store.compute_returns('TEST') is None
