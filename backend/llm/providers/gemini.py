"""Gemini provider placeholder wrapping the existing Gemini integration point."""
from __future__ import annotations


class GeminiProvider:
    name = "gemini"

    async def call(self, request: dict, timeout: float) -> str:
        raise RuntimeError("Gemini structured provider not configured")
