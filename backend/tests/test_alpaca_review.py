"""Regression coverage for PR 83 rate, credential and history boundaries."""
import datetime as dt
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

import alpaca_md


def test_local_slots_are_serialized(monkeypatch):
    monkeypatch.setattr(alpaca_md, "_last_request_at", 0.0)
    monkeypatch.setattr(alpaca_md, "LOCAL_MIN_INTERVAL_SECONDS", 0.02)
    barrier = threading.Barrier(4)

    def take():
        barrier.wait()
        alpaca_md._pace_locally()
        return time.monotonic()

    with ThreadPoolExecutor(max_workers=4) as pool:
        timestamps = sorted(pool.map(lambda _: take(), range(4)))
    assert all(b - a >= 0.015 for a, b in zip(timestamps, timestamps[1:]))


def test_failed_shared_budget_still_reserves_local_slot():
    table = MagicMock()
    table.update_item.side_effect = ClientError({"Error": {"Code": "AccessDeniedException"}}, "UpdateItem")
    with patch.object(alpaca_md, "_get_budget_table", return_value=table), \
            patch.object(alpaca_md, "_pace_locally") as pace:
        alpaca_md._take_token()
    pace.assert_called_once_with()


def test_conditional_budget_failure_keeps_shared_retry():
    table = MagicMock()
    table.update_item.side_effect = [ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"), {}]
    with patch.object(alpaca_md, "_get_budget_table", return_value=table), \
            patch.object(alpaca_md, "_pace_locally") as pace, patch.object(alpaca_md.time, "sleep"):
        alpaca_md._take_token()
    assert table.update_item.call_count == 2
    pace.assert_not_called()


def test_credentials_never_follow_redirect():
    response = MagicMock(status_code=302)
    with patch.object(alpaca_md, "_credentials", return_value={"APCA-API-KEY-ID": "test"}), \
            patch.object(alpaca_md, "_take_token"), \
            patch.object(alpaca_md.requests, "get", return_value=response) as get:
        with pytest.raises(alpaca_md.AlpacaError, match="redirect refused"):
            alpaca_md._get("/v2/stocks/bars", {})
    assert get.call_args.kwargs["allow_redirects"] is False
    assert get.call_count == 1


@pytest.mark.parametrize("end,expected", [(dt.date(2026, 10, 12), "2026-10-12T11:40:00Z"),
                                            (dt.date(2026, 10, 10), "2026-10-11T00:00:00Z"),
                                            (None, "2026-10-12T11:40:00Z")])
def test_sip_end_caps_today_but_keeps_historical_midnight(end, expected):
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 12, 12, tzinfo=dt.timezone.utc)

    with patch.object(alpaca_md.dt, "datetime", Clock), \
            patch.object(alpaca_md, "_get", return_value={}) as get:
        alpaca_md.daily_bars(["SPY"], dt.date(2026, 1, 1), end, adjustment="all")
    assert get.call_args.args[1]["end"] == expected
    assert get.call_args.args[1]["adjustment"] == "all"
