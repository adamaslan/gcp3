"""Provider-neutral structured LLM gateway with deterministic fallback."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from config.agent_config import DEFAULT_LLM_PROVIDER_ORDER
from llm.budget import RunBudget
from llm.circuit_breaker import CircuitBreaker


class Provider(Protocol):
    name: str

    async def call(self, request: dict[str, Any], timeout: float) -> str: ...


@dataclass
class ProviderResult:
    parsed: BaseModel | None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    ai_degraded: bool = False
    fallback_reason: str | None = None


class DisabledProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    async def call(self, request: dict[str, Any], timeout: float) -> str:
        raise RuntimeError(f"{self.name} provider is not configured")


_BREAKER = CircuitBreaker()


async def structured_llm_call(
    request: dict[str, Any],
    schema: type[BaseModel],
    budget: RunBudget,
    fallback_policy: dict[str, Any] | None = None,
) -> ProviderResult:
    provider_order = (fallback_policy or {}).get("providers", DEFAULT_LLM_PROVIDER_ORDER)
    providers = [DisabledProvider(name) for name in provider_order]
    attempts: list[dict[str, Any]] = []
    if not budget.spend():
        return ProviderResult(None, [{"status": "budget_skipped"}], ai_degraded=True, fallback_reason="budget_exhausted")
    for provider in providers:
        if not _BREAKER.allow(provider.name):
            attempts.append({"provider": provider.name, "status": "circuit_open"})
            continue
        try:
            text = await provider.call(request, timeout=(fallback_policy or {}).get("timeout_seconds", 45))
            data = json.loads(text)
            parsed = schema.model_validate(data)
            _BREAKER.record_success(provider.name)
            attempts.append({"provider": provider.name, "status": "ok", "schema_valid": True})
            return ProviderResult(parsed, attempts)
        except Exception as exc:
            _BREAKER.record_failure(provider.name)
            attempts.append({"provider": provider.name, "status": "failed", "schema_valid": False, "error": str(exc)[:240]})
    return ProviderResult(None, attempts, ai_degraded=True, fallback_reason="all_providers_failed")
