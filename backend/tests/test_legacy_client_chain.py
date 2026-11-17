"""The OpenRouter chain has a total deadline and no retired models."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import legacy_client


def test_chain_deadline_falls_through_to_mistral(monkeypatch):
    async def slow_chain(_prompt):
        await asyncio.sleep(5)

    monkeypatch.setattr(legacy_client, "_CHAIN_DEADLINE_SECONDS", 0.05)
    monkeypatch.setattr(legacy_client, "_call_openrouter", slow_chain)
    monkeypatch.setattr(legacy_client, "_call_mistral", AsyncMock(return_value="from mistral"))

    assert asyncio.run(legacy_client.call_llm("hi")) == "from mistral"


def test_chain_has_no_retired_models():
    retired = {"qwen/qwen3-235b-a22b:free", "qwen/qwen3-30b-a3b:free",
               "meta-llama/llama-3.3-70b-instruct:free"}
    assert not retired & set(legacy_client._OPENROUTER_MODEL_CHAIN)
