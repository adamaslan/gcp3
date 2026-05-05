"""Per-run LLM budget accounting."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RunBudget:
    run_id: str
    max_llm_calls_per_run: int = 5
    calls_used: int = 0

    def can_spend(self) -> bool:
        return self.calls_used < self.max_llm_calls_per_run

    def spend(self) -> bool:
        if not self.can_spend():
            return False
        self.calls_used += 1
        return True

