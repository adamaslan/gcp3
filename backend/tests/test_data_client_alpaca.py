"""Alpaca-first quote chain in data_client (network mocked)."""
import asyncio
from unittest.mock import patch

import pytest

import data_client


def _run(coro):
    """Run on a private loop; asyncio.run() would clear the global loop other tests rely on."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _snap(price: float, prev: float) -> dict:
    return {"price": price, "prev_close": prev, "day_open": prev, "day_high": price + 1,
            "day_low": prev - 1, "feed": "iex", "ts": "2026-10-07T19:59:00Z"}


@pytest.fixture(autouse=True)
def _alpaca_env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_API_SECRET", "s")
    for name in ("K_SERVICE", "GITHUB_ACTIONS", "MODAL_TASK_ID", "SIGNALS_ENV"):
        monkeypatch.delenv(name, raising=False)


def test_alpaca_quotes_are_shaped_like_other_sources():
    with patch.object(data_client.alpaca_md, "latest_prices", return_value={"SPY": _snap(110.0, 100.0)}):
        q = data_client._alpaca_quotes_sync(["SPY"])["SPY"]
    assert q["source"] == "alpaca" and q["feed"] == "iex"
    assert q["price"] == 110.0 and q["change"] == 10.0 and q["change_pct"] == 10.0
    assert q["prev_close"] == 100.0 and q["high"] == 111.0


def test_alpaca_failure_returns_empty_and_warns(caplog):
    with patch.object(data_client.alpaca_md, "latest_prices",
                      side_effect=data_client.alpaca_md.AlpacaError("boom")):
        assert data_client._alpaca_quotes_sync(["SPY"]) == {}
    assert "market-data fallback" in caplog.text


def test_get_quotes_uses_alpaca_and_skips_finnhub_when_all_priced():
    with patch.object(data_client, "_alpaca_quotes_sync",
                      return_value={"A": {"price": 1.0, "source": "alpaca"}}), \
            patch.object(data_client, "_finnhub_quote") as fh:
        out = _run(data_client.get_quotes(["A"]))
    assert out["A"]["source"] == "alpaca"
    fh.assert_not_called()


def test_get_quotes_sends_only_unpriced_symbols_to_finnhub():
    async def fake_fh(_client, sym):
        return {"price": 2.0, "source": "finnhub"}

    with patch.object(data_client, "_alpaca_quotes_sync",
                      return_value={"A": {"price": 1.0, "source": "alpaca"}}), \
            patch.object(data_client, "_finnhub_quote", side_effect=fake_fh) as fh:
        out = _run(data_client.get_quotes(["A", "B"]))
    assert out["B"]["source"] == "finnhub"
    assert [c.args[1] for c in fh.call_args_list] == ["B"]


def test_datacenter_host_never_calls_yfinance(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "svc")

    async def failing_fh(_client, sym):
        raise ValueError("no data")

    with patch.object(data_client, "_alpaca_quotes_sync", return_value={}), \
            patch.object(data_client, "_finnhub_quote", side_effect=failing_fh), \
            patch.object(data_client, "_yf_bulk_sync") as yf_bulk:
        out = _run(data_client.get_quotes(["Z"]))
    assert out == {}
    yf_bulk.assert_not_called()


def test_get_quote_prefers_alpaca():
    with patch.object(data_client, "_alpaca_quotes_sync",
                      return_value={"A": {"price": 1.0, "source": "alpaca"}}), \
            patch.object(data_client, "_finnhub_quote") as fh:
        assert _run(data_client.get_quote("A"))["source"] == "alpaca"
    fh.assert_not_called()
