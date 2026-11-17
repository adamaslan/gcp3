"""Seeding never joins incompatible price bases or truncates a long gap."""
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import seed_and_report as seed


def frame(n=120):
    return pd.DataFrame({"adjusted_close": range(1, n + 1), "volume": [10] * n},
                        index=pd.date_range("2025-01-01", periods=n))


@pytest.mark.parametrize("configured", [True, False])
def test_datacenter_extraction_failure_propagates(configured):
    with patch.object(seed.alpaca_md, "is_configured", return_value=configured), \
            patch.object(seed.alpaca_md, "on_datacenter_host", return_value=True), \
            patch.object(seed.alpaca_md, "daily_bars_frames", side_effect=seed.alpaca_md.AlpacaError("unavailable")):
        with pytest.raises(seed.alpaca_md.AlpacaError):
            seed._alpaca_history(["ETF"], 3650)


def test_etf_extraction_requests_all_adjustments():
    data = frame().rename(columns={"adjusted_close": "Close", "volume": "Volume"})
    with patch.object(seed.alpaca_md, "is_configured", return_value=True), \
            patch.object(seed.alpaca_md, "daily_bars_frames", return_value={"ETF": data}) as fetch:
        assert len(seed._alpaca_history(["ETF"], 3650)["ETF"]) == 120
    fetch.assert_called_once_with(["ETF"], 3650, adjustment="all")


def run_seed(meta, datacenter=True, yf_frame=None):
    store = MagicMock()
    store.get_metadata.return_value = meta
    store.append_daily.return_value = 119
    store.store_history.return_value = 120
    industry = MagicMock(_FLAT={"sector": ("name", "ETF")})
    with patch.dict(sys.modules, {"etf_store": store, "industry": industry}), \
            patch.object(seed, "_alpaca_history", return_value={"ETF": frame()}), \
            patch.object(seed.alpaca_md, "on_datacenter_host", return_value=datacenter), \
            patch.object(seed, "_yf_fetch", return_value=yf_frame) as yf:
        if meta and meta["source"] == "yfinance_seed" and datacenter:
            with pytest.raises(seed.alpaca_md.AlpacaError):
                seed.main()
        else:
            seed.main()
    return store, yf


def test_legacy_history_fails_closed_on_datacenter():
    store, yf = run_seed({"source": "yfinance_seed", "last_date": "2025-01-01"})
    store.append_daily.assert_not_called()
    store.store_history.assert_not_called()
    yf.assert_not_called()


def test_all_adjusted_delta_passes_every_new_row_not_just_last_90():
    store, yf = run_seed({"source": "alpaca_all_seed", "last_date": "2025-01-01"})
    assert len(store.append_daily.call_args.args[1]) == 119
    assert store.append_daily.call_args.kwargs["source"] == "alpaca_all_delta"
    yf.assert_not_called()


def test_new_history_uses_all_adjusted_provenance():
    store, _ = run_seed(None)
    assert store.store_history.call_args.kwargs["source"] == "alpaca_all_seed"


def test_local_legacy_history_uses_yfinance_only():
    data = frame().rename(columns={"adjusted_close": "Close", "volume": "Volume"})
    store, yf = run_seed({"source": "yfinance_seed", "last_date": "2025-01-01"}, False, data)
    yf.assert_called_once_with("ETF", "max")
    assert store.append_daily.call_args.kwargs["source"] == "yfinance_delta"


def test_alpaca_series_cannot_receive_yfinance_gap_fill():
    store = MagicMock()
    store.get_metadata.return_value = {"source": "alpaca_all_delta", "last_date": "2025-01-01"}
    industry = MagicMock(_FLAT={"sector": ("name", "ETF")})
    with patch.dict(sys.modules, {"etf_store": store, "industry": industry}), \
            patch.object(seed, "_alpaca_history", return_value={}), \
            patch.object(seed.alpaca_md, "on_datacenter_host", return_value=False), \
            patch.object(seed, "_yf_fetch") as yf:
        with pytest.raises(seed.alpaca_md.AlpacaError):
            seed.main()
    yf.assert_not_called()
    store.append_daily.assert_not_called()


def test_yfinance_storage_explicitly_uses_dividend_adjusted_prices():
    fake_yf = MagicMock()
    with patch.dict(sys.modules, {"yfinance": fake_yf}):
        seed._yf_fetch("ETF", "max")
    fake_yf.Ticker.return_value.history.assert_called_once_with(period="max", auto_adjust=True)
