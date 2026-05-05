"""Small per-provider circuit breaker for optional LLM calls."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class CircuitState:
    state: str = "closed"
    failures: int = 0
    opened_at: datetime | None = None


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 300) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self._states: dict[str, CircuitState] = {}

    def allow(self, provider: str) -> bool:
        state = self._states.setdefault(provider, CircuitState())
        if state.state != "open":
            return True
        if state.opened_at and datetime.now(timezone.utc) - state.opened_at >= self.cooldown:
            state.state = "half-open"
            return True
        return False

    def record_success(self, provider: str) -> None:
        self._states[provider] = CircuitState()

    def record_failure(self, provider: str) -> None:
        state = self._states.setdefault(provider, CircuitState())
        state.failures += 1
        if state.failures >= self.failure_threshold:
            state.state = "open"
            state.opened_at = datetime.now(timezone.utc)

