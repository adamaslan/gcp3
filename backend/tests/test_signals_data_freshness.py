"""Deterministic tests for stored-history as-of tracking and call gating.

Covers the batch-timestamp blind spot: a fresh recompute over stale stored
bars must surface as stale/unknown, and calls (including HOLD) must be
withheld — never emitted as a current recommendation.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date

import pandas as pd
import pytest

import etf_store
import technical_signals
from market_calendar import trading_day_gap
from technical_signals import _data_as_of_score, _score_etf, ENGINE_VERSION


# --- trading_day_gap ---------------------------------------------------------

class TestTradingDayGap:
    def test_same_day_is_zero(self):
        assert trading_day_gap(date(2026, 11, 5), date(2026, 11, 5)) == 0

    def test_end_before_start_is_zero(self):
        assert trading_day_gap(date(2026, 11, 5), date(2026, 11, 4)) == 0

    def test_one_trading_day(self):
        # Wed Nov 4 -> Thu Nov 5 2026: one session in between
        assert trading_day_gap(date(2026, 11, 4), date(2026, 11, 5)) == 1

    def test_weekend_counts_only_sessions(self):
        # Fri Nov 6 -> Mon Nov 9 2026: only Monday counts
        assert trading_day_gap(date(2026, 11, 6), date(2026, 11, 9)) == 1

    def test_week_old_history(self):
        # Fri Oct 30 -> Thu Nov 5 2026: Nov 2,3,4,5 = 4 sessions
        assert trading_day_gap(date(2026, 10, 30), date(2026, 11, 5)) == 4

    def test_holiday_skipped(self):
        # Wed Nov 25 -> Fri Nov 27 2026: Thanksgiving Nov 26 skipped
        assert trading_day_gap(date(2026, 11, 25), date(2026, 11, 27)) == 1


# --- _data_as_of_score --------------------------------------------------------

class TestDataAsOfScore:
    TODAY = date(2026, 11, 5)  # Thursday, trading day

    def test_same_day_fresh(self):
        assert _data_as_of_score("2026-11-05", self.TODAY) == "fresh"

    def test_one_session_behind_fresh(self):
        # Seed runs after close; previous completed session is still fresh
        assert _data_as_of_score("2026-11-04", self.TODAY) == "fresh"

    def test_week_old_stale(self):
        assert _data_as_of_score("2026-10-30", self.TODAY) == "stale"

    def test_missing_unknown(self):
        assert _data_as_of_score(None, self.TODAY) == "unknown"
        assert _data_as_of_score("", self.TODAY) == "unknown"

    def test_unparseable_unknown(self):
        assert _data_as_of_score("not-a-date", self.TODAY) == "unknown"
        assert _data_as_of_score(20261105, self.TODAY) == "unknown"  # wrong type

    def test_future_dated_unknown(self):
        # The seed only writes completed sessions; a bar dated after the most
        # recent completed trading day is anomalous, not "fresh".
        assert _data_as_of_score("2026-11-06", self.TODAY) == "unknown"
        assert _data_as_of_score("2027-01-04", self.TODAY) == "unknown"


# --- etf_store.compute_returns as_of -----------------------------------------

def _fake_history():
    # Newest-first, mirroring load_history's sort order
    idx = pd.to_datetime(["2026-11-05", "2026-11-04", "2026-11-03"])
    return pd.DataFrame({"adjusted_close": [101.0, 100.0, 99.0]}, index=idx)


class TestComputeReturnsAsOf:
    def test_as_of_is_newest_stored_bar(self, monkeypatch):
        monkeypatch.setattr(etf_store, "load_history", lambda symbol: _fake_history())
        returns = etf_store.compute_returns("XLE")
        assert returns["as_of"] == "2026-11-05"
        assert returns["1d"] == pytest.approx(1.0)

    def test_no_history_returns_none(self, monkeypatch):
        monkeypatch.setattr(etf_store, "load_history", lambda symbol: None)
        assert etf_store.compute_returns("XLE") is None


# --- _score_etf freshness gating ----------------------------------------------

def _bullish_row(**overrides):
    row = {
        "etf": "XLE",
        "industry": "Oil & Gas",
        "returns": {"1d": 2.0, "1w": 3.0, "1m": 5.0, "3m": 6.0, "1y": 30.0, "6m": 15.0},
        "52w_high": 100.0,
        "52w_low": 60.0,
        "updated": "2026-11-05T22:00:00+00:00",
        "data_as_of": "2026-11-05",
    }
    row.update(overrides)
    return row


class TestScoreEtfFreshnessGate:
    TODAY = date(2026, 11, 5)

    def test_fresh_data_keeps_buy(self):
        out = _score_etf(_bullish_row(), rank_1d=1, total=54, today=self.TODAY)
        assert out["ai_action"] == "BUY"
        assert out["data_quality_score"] == "fresh"
        assert out["data_as_of"] == "2026-11-05"

    def test_stale_data_withholds_call(self):
        out = _score_etf(_bullish_row(data_as_of="2026-10-30"), rank_1d=1, total=54, today=self.TODAY)
        assert out["ai_action"] == "WITHHELD"
        assert out["data_quality_score"] == "stale"
        assert out["data_as_of"] == "2026-10-30"
        assert "withheld" in out["ai_outlook"]
        assert "BUY" in out["ai_outlook"]  # names the suppressed call
        # Score itself is preserved — it describes the dated data
        assert out["confluence_score"] > 0

    def test_unknown_as_of_withholds_call(self):
        row = _bullish_row()
        del row["data_as_of"]
        out = _score_etf(row, rank_1d=1, total=54, today=self.TODAY)
        assert out["ai_action"] == "WITHHELD"
        assert out["data_quality_score"] == "unknown"

    def test_future_dated_withholds_call(self):
        out = _score_etf(_bullish_row(data_as_of="2026-11-06"), rank_1d=1, total=54, today=self.TODAY)
        assert out["ai_action"] == "WITHHELD"
        assert out["data_quality_score"] == "unknown"

    def test_stale_hold_also_withheld(self):
        # A HOLD computed from stale data must not masquerade as a current
        # "stay put" recommendation either.
        row = _bullish_row(returns={"1d": 0.1, "1w": -0.2}, data_as_of="2026-10-30")
        out = _score_etf(row, rank_1d=27, total=54, today=self.TODAY)
        assert out["ai_action"] == "WITHHELD"
        assert out["data_quality_score"] == "stale"
        assert "withheld" in out["ai_outlook"]

    def test_hold_not_rewritten_by_gate(self):
        # A genuine HOLD from fresh mixed data stays HOLD without the withheld note
        row = _bullish_row(returns={"1d": 0.1, "1w": -0.2})
        out = _score_etf(row, rank_1d=27, total=54, today=self.TODAY)
        assert out["ai_action"] == "HOLD"
        assert "withheld" not in out["ai_outlook"]

    def test_engine_version_bumped(self):
        assert ENGINE_VERSION != "technical_signals@1.0.0"


# --- batch-level aggregation in get_technical_signals -------------------------

def _run_batch(industries, symbol=None):
    """Drive get_technical_signals with a fixed trading date and canned rows."""
    async def fake_returns(force: bool = False) -> dict:
        return {
            "date": "2026-11-05",
            "updated": "2026-11-05T22:00:00+00:00",
            "data_as_of": max(
                (i["data_as_of"] for i in industries if i.get("data_as_of")),
                default=None,
            ),
            "industries": industries,
        }

    async def go():
        technical_signals.get_industry_returns, orig = fake_returns, technical_signals.get_industry_returns
        technical_signals.trading_date, orig_td = lambda: date(2026, 11, 5), technical_signals.trading_date
        technical_signals.get_cache, orig_gc = lambda k: None, technical_signals.get_cache
        technical_signals.set_cache, orig_sc = lambda *a, **k: None, technical_signals.set_cache
        try:
            return await technical_signals.get_technical_signals(symbol=symbol)
        finally:
            technical_signals.get_industry_returns = orig
            technical_signals.trading_date = orig_td
            technical_signals.get_cache = orig_gc
            technical_signals.set_cache = orig_sc

    return asyncio.run(go())


class TestBatchFreshnessAggregation:
    def test_one_stale_row_marks_batch_stale(self):
        # 1 fresh + 1 stale: batch headline must not hide the stale row
        rows = [
            _bullish_row(),  # fresh, as_of 2026-11-05
            _bullish_row(etf="HACK", industry="Cybersecurity", data_as_of="2026-10-30"),
        ]
        out = _run_batch(rows)
        assert out["data_quality_score"] == "stale"
        # fresh row keeps its call; stale row is withheld
        assert out["symbols"]["XLE"]["ai_action"] == "BUY"
        assert out["symbols"]["HACK"]["ai_action"] == "WITHHELD"
        assert out["signal_summary"]["withheld_count"] == 1

    def test_all_stale_regime_indeterminate(self):
        rows = [
            _bullish_row(data_as_of="2026-10-30"),
            _bullish_row(etf="HACK", industry="Cybersecurity", data_as_of="2026-10-30"),
        ]
        out = _run_batch(rows)
        assert out["data_quality_score"] == "stale"
        assert out["signal_summary"]["ai_regime"] == "Indeterminate"
        assert out["signal_summary"]["buy_count"] == 0

    def test_single_symbol_batch_matches_row(self):
        rows = [
            _bullish_row(),  # XLE fresh
            _bullish_row(etf="HACK", industry="Cybersecurity", data_as_of="2026-10-30"),
        ]
        out = _run_batch(rows, symbol="HACK")
        assert out["data_quality_score"] == "stale"
        assert out["symbols"]["HACK"]["ai_action"] == "WITHHELD"

    def test_all_fresh_batch_fresh(self):
        rows = [_bullish_row(), _bullish_row(etf="HACK", industry="Cybersecurity")]
        out = _run_batch(rows)
        assert out["data_quality_score"] == "fresh"


# --- session settle margin (partial-bar defense) -------------------------------

from datetime import datetime, timezone
import market_calendar
from market_calendar import session_settled, today_et


class TestSessionSettled:
    def test_boundaries(self):
        assert session_settled(datetime(2026, 11, 5, 22, 29, tzinfo=timezone.utc)) is False
        assert session_settled(datetime(2026, 11, 5, 22, 30, tzinfo=timezone.utc)) is True
        assert session_settled(datetime(2026, 11, 5, 23, 59, tzinfo=timezone.utc)) is True
        assert session_settled(datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)) is False
        assert session_settled(datetime(2026, 11, 6, 14, 30, tzinfo=timezone.utc)) is False  # 9:30am ET

    def test_today_et_returns_date(self):
        assert isinstance(today_et(), date)


class TestDropUnsettledToday:
    """Storage-layer gate: etf_store drops today's bar before the settle margin,
    for every ingest caller."""

    def _hist(self):
        idx = pd.to_datetime(["2026-11-06", "2026-11-05", "2026-11-04"])
        return pd.DataFrame({"adjusted_close": [3.0, 2.0, 1.0], "volume": [1, 1, 1]}, index=idx)

    def test_partial_bar_dropped_before_settle(self):
        import etf_store
        with patch("etf_store.session_settled", return_value=False), \
             patch("etf_store.today_et", return_value=date(2026, 11, 6)):
            out = etf_store._drop_unsettled_today(self._hist())
        assert [d.strftime("%Y-%m-%d") for d in out.index] == ["2026-11-05", "2026-11-04"]

    def test_final_bar_kept_after_settle(self):
        import etf_store
        with patch("etf_store.session_settled", return_value=True), \
             patch("etf_store.today_et", return_value=date(2026, 11, 6)):
            out = etf_store._drop_unsettled_today(self._hist())
        assert len(out) == 3

    def test_append_daily_drops_partial_today_pre_settle(self):
        # A 9:30am partial bar via ANY caller (seed, CLI, admin route) never lands
        import etf_store
        fake_collection = MagicMock()
        df = pd.DataFrame(
            {"adjusted_close": [105.0], "volume": [5000]},
            index=pd.to_datetime(["2026-11-06"]),
        )
        with patch("etf_store.session_settled", return_value=False), \
             patch("etf_store.today_et", return_value=date(2026, 11, 6)), \
             patch("etf_store._db") as mock_db, \
             patch("etf_store.get_metadata") as mock_meta:
            mock_db.return_value.collection.return_value = fake_collection
            mock_meta.return_value = {
                "symbol": "TEST", "last_date": "2026-11-05", "total_days": 1,
                "storage_mode": "embedded",
                "prices": [{"date": "2026-11-05", "adjusted_close": 100.0, "volume": 1000}],
            }
            n = etf_store.append_daily("TEST", df, source="yfinance_delta")
        assert n == 0
        fake_collection.document.assert_not_called()  # nothing even opened for write


# --- append_daily same-session replacement --------------------------------------

from unittest.mock import MagicMock, patch


class TestAppendDailySameSessionReplace:
    def test_todays_bar_is_replaced_not_duplicated(self):
        import etf_store
        today = market_calendar.today_et().isoformat()
        fake_doc = MagicMock()
        fake_doc.exists = True
        fake_doc.to_dict.return_value = {
            "symbol": "TEST", "last_date": today, "total_days": 1,
            "storage_mode": "embedded",
            "prices": [{"date": today, "adjusted_close": 100.0, "volume": 1000}],  # 9:30am partial
        }
        fake_ref = MagicMock()
        fake_ref.get.return_value = fake_doc
        fake_collection = MagicMock()
        fake_collection.document.return_value = fake_ref

        idx = pd.to_datetime([today])
        df = pd.DataFrame({"adjusted_close": [105.0], "volume": [5000]}, index=idx)  # final bar

        with patch("etf_store._db") as mock_db, patch("etf_store.get_metadata") as mock_meta, \
             patch("etf_store.session_settled", return_value=True):
            mock_db.return_value.collection.return_value = fake_collection
            mock_meta.return_value = fake_doc.to_dict()
            n = etf_store.append_daily("TEST", df, source="yfinance_delta")

        assert n == 0  # no new day added...
        updates = [c.args[0] for c in fake_ref.update.call_args_list]
        price_updates = [u["prices"] for u in updates if isinstance(u, dict) and isinstance(u.get("prices"), list)]
        assert price_updates, f"expected a prices-array replacement, got {updates}"
        replaced = price_updates[0]
        assert len(replaced) == 1 and replaced[0]["adjusted_close"] == 105.0  # ...final overwrites partial
        meta_update = updates[-1]
        assert meta_update["total_days"] == 1  # replacement is not a new day

    def test_historical_same_date_still_skipped(self):
        # The 2026-05-15 dual-source guard: same PAST date, different price -> skip
        import etf_store
        fake_doc = MagicMock()
        fake_doc.exists = True
        fake_doc.to_dict.return_value = {
            "symbol": "TEST", "last_date": "2026-05-13", "total_days": 1,
            "storage_mode": "embedded",
            "prices": [{"date": "2026-05-13", "adjusted_close": 100.0, "volume": 1000}],
        }
        fake_ref = MagicMock()
        fake_ref.get.return_value = fake_doc
        fake_collection = MagicMock()
        fake_collection.document.return_value = fake_ref

        idx = pd.to_datetime(["2026-05-13"])
        df = pd.DataFrame({"adjusted_close": [99999.0], "volume": [1]}, index=idx)

        with patch("etf_store._db") as mock_db, patch("etf_store.get_metadata") as mock_meta:
            mock_db.return_value.collection.return_value = fake_collection
            mock_meta.return_value = fake_doc.to_dict()
            n = etf_store.append_daily("TEST", df, source="finnhub_delta")

        assert n == 0
        fake_ref.update.assert_not_called()  # nothing written at all
