"""Offline regression coverage for PR81 provider and agent budgets."""
import asyncio
import copy
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from agents.base import AgentLoop
from llm import openrouter_client as client


class Result(BaseModel):
    value: int = 0


def test_strict_payload_does_not_change_public_schema():
    schema = {"type": "object", "properties": {"items": {"type": "array", "items": {"$ref": "#/$defs/Item"}}}, "$defs": {"Item": {"type": "object", "properties": {"value": {"type": "integer", "default": 1}}}}}
    original = copy.deepcopy(schema)
    sent = client._payload([], "test", schema, 0.1)["response_format"]["json_schema"]["schema"]
    assert schema == original
    assert sent["required"] == ["items"]
    assert sent["additionalProperties"] is False
    assert sent["$defs"]["Item"]["required"] == ["value"]
    assert sent["$defs"]["Item"]["additionalProperties"] is False
    assert "default" not in sent["$defs"]["Item"]["properties"]["value"]


@pytest.mark.parametrize("asynchronous", [False, True])
def test_deadline_spans_models_and_caps_request(monkeypatch, asynchronous):
    clock = [0.0]
    seen = []
    monkeypatch.setattr(client.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(client, "_headers", lambda: {})
    monkeypatch.setattr(client, "_models", lambda online: ("one", "two", "three"))

    def fake_post(*args, **kwargs):
        seen.append(kwargs["timeout"])
        clock[0] += 2
        raise httpx.ConnectError("offline")

    class Sync:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        post = staticmethod(fake_post)

    class Async:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return fake_post(*args, **kwargs)

    monkeypatch.setattr(client.httpx, "Client", Sync)
    monkeypatch.setattr(client.httpx, "AsyncClient", Async)
    with pytest.raises(client.OpenRouterError, match="deadline"):
        if asynchronous:
            asyncio.run(client.complete([], deadline_seconds=3))
        else:
            client.complete_sync([], deadline_seconds=3)
    assert seen == [3, 1]


@pytest.mark.parametrize("asynchronous", [False, True])
def test_backoff_does_not_exceed_deadline(monkeypatch, asynchronous):
    calls = []
    monkeypatch.setattr(client, "_headers", lambda: {})
    monkeypatch.setattr(client, "_models", lambda online: ("one", "two"))
    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"]["model"])
        response = httpx.Response(429, request=httpx.Request("POST", client.URL))
        response.raise_for_status()
    class Sync:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        post = staticmethod(fake_post)
    class Async:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return fake_post(*args, **kwargs)
    def fail_sleep(*args): pytest.fail("backoff exceeds budget")
    monkeypatch.setattr(client.httpx, "Client", Sync)
    monkeypatch.setattr(client.httpx, "AsyncClient", Async)
    monkeypatch.setattr(client.time, "sleep", fail_sleep)
    monkeypatch.setattr(client.asyncio, "sleep", fail_sleep)
    with pytest.raises(client.OpenRouterError):
        if asynchronous: asyncio.run(client.complete([], deadline_seconds=1))
        else: client.complete_sync([], deadline_seconds=1)
    assert calls == ["one", "two"]


def test_agent_timeout_skips_one_shot_after_budget(monkeypatch):
    import agents.base as base
    calls = []
    async def slow_complete(messages, **kwargs):
        calls.append(kwargs["deadline_seconds"])
        await asyncio.sleep(1)
    monkeypatch.setattr(base, "MAX_WALLCLOCK_SECONDS", 0.02)
    monkeypatch.setattr(client, "complete", slow_complete)
    result, session = asyncio.run(AgentLoop("test").run(None, {}, Result, fallback_fn=lambda: {"value": 3}))
    assert result.value == 3
    assert session.budget_exceeded and session.fallback_used
    assert len(calls) == 1
    assert calls[0] <= 0.02


@pytest.mark.parametrize("module_name, method", [("macro_agent", "run_macro"), ("market_overview_agent", "run_overview")])
def test_grounding_runs_outside_event_loop(monkeypatch, module_name, method):
    import importlib
    import threading
    module = importlib.import_module(f"agents.{module_name}")
    main_thread = threading.get_ident()
    def grounded(**kwargs):
        assert threading.get_ident() != main_thread
        return SimpleNamespace(text="grounded")
    async def run(self, **kwargs): return kwargs["initial_context"], None
    monkeypatch.setattr(module, "generate_grounded", grounded)
    monkeypatch.setattr(AgentLoop, "run", run)
    agent_type = module.MacroAgent if module_name == "macro_agent" else module.MarketOverviewAgent
    result, _ = asyncio.run(getattr(agent_type(), method)({}, Result))
    assert result["grounded_news_summary"] == "grounded"


@pytest.mark.parametrize("job, expected", [("returns", "app exited"), ("fetch", "FINNHUB_API_KEY unavailable for job fetch"), ("midday-yf", "FINNHUB_API_KEY unavailable for job midday-yf"), ("purge", "app exited"), ("seed", "app exited"), ("audit", "app exited")])
def test_backup_key_requirement_is_per_job(tmp_path, monkeypatch, job, expected):
    import os
    import subprocess
    from pathlib import Path
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in {"gcloud": "exit 1", "openssl": "echo test-only-token", "lsof": "exit 1", "python": "exit 1"}.items():
        stub = bindir / name
        stub.write_text("#!/bin/sh\n" + body + "\n")
        stub.chmod(0o700)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}
    env.pop("FINNHUB_API_KEY", None)
    script = Path(__file__).parents[1] / "run_local_backup.sh"
    completed = subprocess.run(["bash", str(script), job], env=env, capture_output=True, text=True, timeout=5)
    assert completed.returncode == 1
    assert expected in completed.stderr
    if job not in {"fetch", "midday-yf"}:
        assert "FINNHUB_API_KEY unavailable for job" not in completed.stderr


def test_backup_rejects_existing_listener_before_boot(tmp_path):
    import os
    import subprocess
    from pathlib import Path
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in {"gcloud": "exit 1", "openssl": "echo test-only-token", "lsof": "echo 12345", "python": "echo unexpected-boot >&2; exit 1"}.items():
        stub = bindir / name
        stub.write_text("#!/bin/sh\n" + body + "\n")
        stub.chmod(0o700)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}
    script = Path(__file__).parents[1] / "run_local_backup.sh"
    completed = subprocess.run(["bash", str(script), "--dry-run"], env=env, capture_output=True, text=True, timeout=5)
    assert completed.returncode == 1
    assert "already has a listener" in completed.stderr
    assert "unexpected-boot" not in completed.stderr


def test_async_provider_is_cancelled_at_total_deadline(monkeypatch):
    cancelled = []
    monkeypatch.setattr(client, "_headers", lambda: {})
    monkeypatch.setattr(client, "_models", lambda online: ("one", "two"))
    class Async:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            try:
                await asyncio.sleep(1)
            finally:
                cancelled.append(True)
    monkeypatch.setattr(client.httpx, "AsyncClient", Async)
    with pytest.raises(client.OpenRouterError, match="deadline"):
        asyncio.run(client.complete([], deadline_seconds=0.02))
    assert cancelled == [True]
