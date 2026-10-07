"""history_client: Alpaca first, yfinance local only, fail closed on datacenter hosts."""
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import history_client


def _frame(n: int = 5) -> pd.DataFrame:
    return pd.DataFrame({"Open": [1.0] * n, "High": [1.0] * n, "Low": [1.0] * n,
                         "Close": [1.0] * n, "Volume": [10] * n},
                        index=pd.date_range("2026-10-01", periods=n, freq="B"))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")
    for name in ("K_SERVICE", "GITHUB_ACTIONS", "MODAL_TASK_ID", "SIGNALS_ENV"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("period,expected", [("2d", 9), ("5d", 12), ("3mo", 100), ("2y", 739), ("max", 3650)])
def test_period_to_days(period, expected):
    assert history_client.period_to_days(period) == expected


def test_period_to_days_rejects_unknown():
    with pytest.raises(ValueError):
        history_client.period_to_days("fortnight")


def test_uses_alpaca_when_it_has_bars():
    with patch.object(history_client.alpaca_md, "daily_bars_frames", return_value={"SPY": _frame()}) as bars:
        out = history_client.daily_history("SPY", "3mo")
    assert len(out) == 5
    bars.assert_called_once_with(["SPY"], 100)


def test_local_run_falls_back_to_yfinance():
    fake_yf = MagicMock()
    fake_yf.Ticker.return_value.history.return_value = _frame(3)
    with patch.object(history_client.alpaca_md, "daily_bars_frames", return_value={}), \
            patch.dict("sys.modules", {"yfinance": fake_yf}):
        out = history_client.daily_history("ZZZ", "3mo")
    assert len(out) == 3
    fake_yf.Ticker.return_value.history.assert_called_once_with(period="3mo")


def test_datacenter_host_returns_empty_without_calling_yfinance(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "svc")
    fake_yf = MagicMock()
    with patch.object(history_client.alpaca_md, "daily_bars_frames", return_value={}), \
            patch.dict("sys.modules", {"yfinance": fake_yf}):
        out = history_client.daily_history("ZZZ", "3mo")
    assert out.empty
    fake_yf.Ticker.assert_not_called()


def test_ytd_days_is_positive():
    assert history_client.period_to_days("ytd") >= (date.today() - date(date.today().year, 1, 1)).days
