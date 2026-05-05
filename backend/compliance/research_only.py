"""Research-only enforcement utilities for finance agents."""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from fastapi import Request, Response


EXECUTION_PHRASES = [
    "place order",
    "submit order",
    "execute trade",
    "buy market",
    "sell market",
    "limit order",
    "stop order",
    "broker submit",
]

_EXECUTION_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in EXECUTION_PHRASES) + r")\b", re.I)


def enforce_research_only(decision: Any) -> Any:
    label = getattr(decision, "compliance_label", None)
    if isinstance(decision, dict):
        label = decision.get("compliance_label", label)
    if label != "research_only":
        raise ValueError("decision must be labeled research_only")
    return decision


def sanitize_response_text(text: str) -> tuple[str, bool]:
    violated = bool(_EXECUTION_RE.search(text))
    if not violated:
        return text, False
    return _EXECUTION_RE.sub("research action", text), True


async def research_only_header_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    if request.url.path.startswith("/agents/"):
        response.headers["X-Research-Only"] = "true"
    return response

