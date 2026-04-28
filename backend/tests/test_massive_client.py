"""Tests for massive_client.py — rate limiting, retries, and backoff logic."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("MASSIVE_API_KEY", "test-polygon-key")

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx

import massive_client as mc


def _mock_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.request = MagicMock()
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=resp.request, response=resp
        )
    return resp


# ── _get retries ──────────────────────────────────────────────────────────────

class TestMassiveClientGet:
    """_get() retry and backoff behaviour."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        ok_resp = _mock_response(200, {"results": []})
        ok_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=ok_resp)

        with patch("massive_client._get_http_client", return_value=mock_client), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await mc._get("https://api.polygon.io/v2/test")

        assert result == {"results": []}
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_429_then_succeeds(self):
        rate_limited = _mock_response(429)
        ok_resp = _mock_response(200, {"results": ["ok"]})
        ok_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[rate_limited, ok_resp])

        with patch("massive_client._get_http_client", return_value=mock_client), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await mc._get("https://api.polygon.io/v2/test")

        assert result == {"results": ["ok"]}
        assert mock_client.get.call_count == 2
        # Should have slept with base delay (2s) for attempt 1
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        rate_limit_sleeps = [s for s in sleep_calls if s >= mc._RETRY_BASE_DELAY]
        assert len(rate_limit_sleeps) >= 1

    @pytest.mark.asyncio
    async def test_backoff_doubles_each_attempt(self):
        """Verify sleep duration doubles: 2s → 4s for two consecutive 429s."""
        rate_limited = _mock_response(429)
        ok_resp = _mock_response(200, {})
        ok_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[rate_limited, rate_limited, ok_resp])

        # Patch only the retry sleep inside the attempt loop, not the rate-limit guard sleep
        retry_sleep_calls = []
        original_sleep = __import__("asyncio").sleep

        async def selective_sleep(duration):
            # The rate-limit guard sleep is always > 10s; retry sleeps are 2s, 4s, 8s
            if duration < 10:
                retry_sleep_calls.append(duration)

        with patch("massive_client._get_http_client", return_value=mock_client), \
             patch("asyncio.sleep", side_effect=selective_sleep):
            await mc._get("https://api.polygon.io/v2/test")

        assert retry_sleep_calls[0] == mc._RETRY_BASE_DELAY         # attempt 1: 2s
        assert retry_sleep_calls[1] == mc._RETRY_BASE_DELAY * 2     # attempt 2: 4s

    @pytest.mark.asyncio
    async def test_exhausts_retries_on_persistent_429(self):
        """After MAX_RETRIES 429s, the last exception is re-raised."""
        rate_limited = _mock_response(429)
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=rate_limited)

        with patch("massive_client._get_http_client", return_value=mock_client), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception):
                await mc._get("https://api.polygon.io/v2/test")

        assert mock_client.get.call_count == mc._MAX_RETRIES

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self):
        ok_resp = _mock_response(200, {"ok": True})
        ok_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[
            httpx.TimeoutException("timed out"),
            ok_resp,
        ])

        with patch("massive_client._get_http_client", return_value=mock_client), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await mc._get("https://api.polygon.io/v2/test")

        assert result == {"ok": True}
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_403_raises_immediately_no_retry(self):
        """403 is a config error — must NOT be retried."""
        forbidden = _mock_response(403)
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=forbidden)

        with patch("massive_client._get_http_client", return_value=mock_client), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await mc._get("https://api.polygon.io/v2/test")

        assert "403" in str(exc_info.value)
        assert mock_client.get.call_count == 1  # no retry on 403

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_immediately(self):
        with patch.dict(os.environ, {}, clear=True):
            # Temporarily blank out the module-level key
            original = mc.MASSIVE_API_KEY
            mc.MASSIVE_API_KEY = ""
            try:
                with pytest.raises(KeyError):
                    await mc._get("https://api.polygon.io/v2/test")
            finally:
                mc.MASSIVE_API_KEY = original


# ── get_snapshots ─────────────────────────────────────────────────────────────

class TestGetSnapshots:
    """get_snapshots() batching and error handling."""

    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty_dict(self):
        result = await mc.get_snapshots([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_reindexed_by_symbol(self):
        raw_response = {
            "results": [
                {"ticker": "AAPL", "c": 180.0},
                {"ticker": "MSFT", "c": 420.0},
            ]
        }
        with patch("massive_client._get", new_callable=AsyncMock, return_value=raw_response):
            result = await mc.get_snapshots(["AAPL", "MSFT"])

        assert "AAPL" in result
        assert "MSFT" in result
        assert result["AAPL"]["c"] == 180.0

    @pytest.mark.asyncio
    async def test_exception_returns_empty_dict(self):
        """API failure should return {} not raise, so caller can degrade gracefully."""
        with patch("massive_client._get", new_callable=AsyncMock, side_effect=Exception("network error")):
            result = await mc.get_snapshots(["AAPL"])
        assert result == {}
