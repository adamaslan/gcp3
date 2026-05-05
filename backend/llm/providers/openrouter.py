"""OpenRouter provider placeholder.

Network calls are intentionally not made unless this provider is extended with
credentials and an HTTP client.
"""
from __future__ import annotations


class OpenRouterProvider:
    name = "openrouter_qwen3"

    async def call(self, request: dict, timeout: float) -> str:
        raise RuntimeError("OPENROUTER_API_KEY not configured")

