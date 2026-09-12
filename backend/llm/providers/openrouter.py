"""OpenRouter provider — qwen/qwen3-235b-a22b via OpenRouter API."""
from __future__ import annotations

import os
from typing import Any

import httpx

_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "qwen/qwen3-235b-a22b"


class OpenRouterProvider:
    name = "openrouter_qwen3"

    async def call(self, request: dict[str, Any], timeout: float) -> str:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not configured")

        messages = request.get("messages") or [
            {"role": "user", "content": request.get("prompt", "")}
        ]

        payload = {
            "model": _MODEL,
            "messages": messages,
            "temperature": request.get("temperature", 0.2),
        }
        if "response_format" in request:
            payload["response_format"] = request["response_format"]

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                _URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        # Strip markdown fences if model wraps JSON in ```json ... ```
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return content
