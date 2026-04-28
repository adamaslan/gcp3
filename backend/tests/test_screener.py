"""Tests for screener.py — cache-only reads and cache-build separation."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest
from fastapi import HTTPException

import screener as screener_module


# ── get_screener_data ─────────────────────────────────────────────────────────

class TestGetScreenerData:
    """get_screener_data() must only read from cache — never touch live APIs."""

    @pytest.mark.asyncio
    async def test_returns_cached_data_on_hit(self):
        fake_cache = {"date": str(date.today()), "total_screened": 42, "gainers": [], "losers": []}
        with patch("screener.get_cache", return_value=fake_cache):
            result = await screener_module.get_screener_data()
        assert result == fake_cache

    @pytest.mark.asyncio
    async def test_raises_503_on_cache_miss(self):
        with patch("screener.get_cache", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await screener_module.get_screener_data()
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_503_detail_is_human_readable(self):
        with patch("screener.get_cache", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await screener_module.get_screener_data()
        assert "nightly refresh" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_never_calls_get_quotes_on_cache_hit(self):
        fake_cache = {"date": str(date.today()), "total_screened": 1}
        with patch("screener.get_cache", return_value=fake_cache):
            with patch("screener.build_screener_cache") as mock_build:
                await screener_module.get_screener_data()
        mock_build.assert_not_called()

    @pytest.mark.asyncio
    async def test_never_calls_get_quotes_on_cache_miss(self):
        """Even on a miss, get_screener_data must not make live API calls."""
        with patch("screener.get_cache", return_value=None):
            with patch("data_client.get_quotes") as mock_gq:
                with pytest.raises(HTTPException):
                    await screener_module.get_screener_data()
        mock_gq.assert_not_called()


# ── build_screener_cache ──────────────────────────────────────────────────────

class TestBuildScreenerCache:
    """build_screener_cache() fetches live quotes and writes with the correct TTL."""

    def _fake_quotes(self) -> dict:
        return {
            "AAPL": {"price": 180.0, "change": 2.0, "change_pct": 1.1, "high": 185.0, "low": 175.0, "open": 178.0, "prev_close": 178.0, "source": "finnhub"},
            "MSFT": {"price": 420.0, "change": 8.0, "change_pct": 1.9, "high": 425.0, "low": 410.0, "open": 412.0, "prev_close": 412.0, "source": "finnhub"},
            "TSLA": {"price": 160.0, "change": -4.0, "change_pct": -2.4, "high": 168.0, "low": 158.0, "open": 165.0, "prev_close": 164.0, "source": "yfinance"},
        }

    @pytest.mark.asyncio
    async def test_writes_cache_with_26h_ttl(self):
        mock_quotes = self._fake_quotes()
        with patch("screener.get_cache", return_value=None), \
             patch("screener.set_cache") as mock_set, \
             patch("data_client.get_quotes", new_callable=AsyncMock, return_value=mock_quotes):
            await screener_module.build_screener_cache()

        mock_set.assert_called_once()
        _, kwargs = mock_set.call_args[0], mock_set.call_args[1]
        args = mock_set.call_args[0]
        # set_cache(key, result, ttl_hours=26)
        assert args[0].startswith("screener:")
        assert mock_set.call_args == call(args[0], args[1], ttl_hours=26)

    @pytest.mark.asyncio
    async def test_result_contains_required_keys(self):
        mock_quotes = self._fake_quotes()
        with patch("screener.get_cache", return_value=None), \
             patch("screener.set_cache"), \
             patch("data_client.get_quotes", new_callable=AsyncMock, return_value=mock_quotes):
            result = await screener_module.build_screener_cache()

        for key in ("date", "total_screened", "gainers", "losers", "signal_counts", "breadth_pct", "ai_regime", "quotes", "sources"):
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_signals_are_attached_to_every_quote(self):
        mock_quotes = self._fake_quotes()
        with patch("screener.get_cache", return_value=None), \
             patch("screener.set_cache"), \
             patch("data_client.get_quotes", new_callable=AsyncMock, return_value=mock_quotes):
            result = await screener_module.build_screener_cache()

        valid_signals = {"strong_buy", "buy", "hold", "sell", "strong_sell"}
        for sym, q in result["quotes"].items():
            assert "signal" in q, f"{sym} missing signal"
            assert q["signal"] in valid_signals, f"{sym} has invalid signal: {q['signal']}"

    @pytest.mark.asyncio
    async def test_total_screened_matches_quote_count(self):
        mock_quotes = self._fake_quotes()
        with patch("screener.get_cache", return_value=None), \
             patch("screener.set_cache"), \
             patch("data_client.get_quotes", new_callable=AsyncMock, return_value=mock_quotes):
            result = await screener_module.build_screener_cache()

        assert result["total_screened"] == len(mock_quotes)

    @pytest.mark.asyncio
    async def test_sources_count_is_accurate(self):
        mock_quotes = self._fake_quotes()  # 2 finnhub, 1 yfinance
        with patch("screener.get_cache", return_value=None), \
             patch("screener.set_cache"), \
             patch("data_client.get_quotes", new_callable=AsyncMock, return_value=mock_quotes):
            result = await screener_module.build_screener_cache()

        assert result["sources"]["finnhub"] == 2
        assert result["sources"]["yfinance"] == 1

    @pytest.mark.asyncio
    async def test_skips_fetch_if_cache_already_populated(self):
        """Stampede guard: second concurrent call reuses the first writer's result."""
        already_cached = {"date": str(date.today()), "total_screened": 99}
        with patch("screener.get_cache", return_value=already_cached), \
             patch("data_client.get_quotes", new_callable=AsyncMock) as mock_gq:
            result = await screener_module.build_screener_cache()

        mock_gq.assert_not_called()
        assert result == already_cached

    @pytest.mark.asyncio
    async def test_cache_key_includes_today(self):
        mock_quotes = self._fake_quotes()
        captured_keys = []
        def capture_set(key, value, ttl_hours):
            captured_keys.append(key)
        with patch("screener.get_cache", return_value=None), \
             patch("screener.set_cache", side_effect=capture_set), \
             patch("data_client.get_quotes", new_callable=AsyncMock, return_value=mock_quotes):
            await screener_module.build_screener_cache()

        assert captured_keys[0] == f"screener:{date.today()}"
