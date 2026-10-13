"""Exercise provider cooldown without market data, credentials, or cloud writes."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm import legacy_client


@pytest.fixture
def summary(monkeypatch):
    cache = {}
    clock = [0]
    storage = ModuleType("firestore")
    storage.get_cache = lambda key: cache[key][0] if key in cache and cache[key][1] > clock[0] else None
    storage.set_cache = Mock(side_effect=lambda key, value, ttl_hours=1, ttl_seconds=None: cache.update(
        {key: (value, clock[0] + (ttl_seconds if ttl_seconds is not None else ttl_hours * 3600))}
    ))
    storage.delete_cache = Mock(side_effect=lambda key: cache.pop(key, None))
    monkeypatch.setitem(sys.modules, "firestore", storage)
    gathers = []
    for name, function in (("morning", "get_morning_brief"), ("sector_rotation", "get_sector_rotation"),
                           ("macro_pulse", "get_macro_pulse"), ("screener", "get_screener_data"),
                           ("news_sentiment", "get_news_sentiment")):
        module = ModuleType(name)
        gather = AsyncMock(return_value={})
        setattr(module, function, gather)
        gathers.append(gather)
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("summary_under_test", Path(__file__).resolve().parents[1] / "ai_summary.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.call_llm = AsyncMock(side_effect=legacy_client.LLMUnavailableError("private provider diagnostic"))
    return module, storage, gathers, clock


def test_failure_skips_gathers_until_expiry_and_then_recovers(summary):
    module, storage, gathers, clock = summary
    for _ in range(2):
        with pytest.raises(legacy_client.LLMUnavailableError, match="temporarily unavailable"):
            asyncio.run(module.get_ai_summary())
    assert module.call_llm.await_count == 1
    assert all(gather.await_count == 1 for gather in gathers)
    assert storage.set_cache.call_args.kwargs == {"ttl_seconds": 600}
    assert "private" not in str(storage.set_cache.call_args)
    clock[0] = 601
    module.call_llm.side_effect = None
    module.call_llm.return_value = "Recovered brief"
    assert asyncio.run(module.get_ai_summary())["brief"] == "Recovered brief"
    assert asyncio.run(module.get_ai_summary())["brief"] == "Recovered brief"
    assert module.call_llm.await_count == 2


def test_scheduled_refresh_respects_cooldown(summary):
    module, _, _, _ = summary
    with pytest.raises(legacy_client.LLMUnavailableError):
        asyncio.run(module.get_ai_summary())
    module.call_llm.side_effect = None
    module.call_llm.return_value = "Manual recovery"
    with pytest.raises(legacy_client.LLMUnavailableError):
        asyncio.run(module.refresh_ai_summary())
    assert module.call_llm.await_count == 1


def test_unrelated_errors_are_not_cached(summary):
    module, storage, _, _ = summary
    module.call_llm.side_effect = ValueError("programming error")
    with pytest.raises(ValueError):
        asyncio.run(module.get_ai_summary())
    storage.set_cache.assert_not_called()


def test_client_raises_specific_failure(monkeypatch):
    monkeypatch.setattr(legacy_client, "_call_openrouter", AsyncMock(side_effect=RuntimeError("primary unavailable")))
    monkeypatch.setattr(legacy_client, "_call_mistral", AsyncMock(side_effect=RuntimeError("fallback unavailable")))
    with pytest.raises(legacy_client.LLMUnavailableError):
        asyncio.run(legacy_client.call_llm("test"))
