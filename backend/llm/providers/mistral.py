"""Mistral provider placeholder."""
from __future__ import annotations


class MistralProvider:
    name = "mistral"

    async def call(self, request: dict, timeout: float) -> str:
        raise RuntimeError("MISTRAL_API_KEY not configured")

