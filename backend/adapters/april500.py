"""Import-safe wrapper for April 500 deep scans.

The external script is optional at runtime. When unavailable or failing, this
adapter emits a failed ToolResult instead of breaking the agent loop.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any

from schemas.april500 import April500ToolResult, April500Signals


class April500Adapter:
    def __init__(self, config: Any | None = None, script_path: str | None = None) -> None:
        self.config = config
        configured_path = script_path or getattr(config, "april500_script_path", None) or os.environ.get("APRIL500_SCRIPT_PATH")
        self.script_path = Path(configured_path) if configured_path else None
        self.timeout_seconds = getattr(config, "april500_timeout_seconds", 30)

    async def scan(self, ticker: str, period: str, run_id: str) -> April500ToolResult:
        inputs_hash = hashlib.sha256(f"{ticker}:{period}:{run_id}".encode()).hexdigest()[:16]
        if self.script_path is None or not self.script_path.exists():
            return April500ToolResult(
                tool_name="april500",
                tool_family="technical",
                inputs_hash=inputs_hash,
                timeframe=period,
                status="skipped",
                net_score=0.0,
                risk_flags=["april500_script_not_configured" if self.script_path is None else "april500_script_missing"],
                evidence=[],
            )
        try:
            # The script's concrete API has changed over time, so keep this adapter
            # conservative: import in a worker and normalize any dict-shaped output.
            result = await asyncio.wait_for(asyncio.to_thread(self._run_imported_scan, ticker, period, run_id), timeout=self.timeout_seconds)
            return self._normalize(result or {}, ticker, period, inputs_hash)
        except asyncio.TimeoutError:
            return April500ToolResult(
                tool_name="april500",
                tool_family="technical",
                inputs_hash=inputs_hash,
                timeframe=period,
                status="failed",
                net_score=0.0,
                risk_flags=["april500_timeout"],
            )
        except Exception as exc:
            return April500ToolResult(
                tool_name="april500",
                tool_family="technical",
                inputs_hash=inputs_hash,
                timeframe=period,
                status="failed",
                net_score=0.0,
                risk_flags=["april500_failed"],
                counter_evidence=[str(exc)[:240]],
            )

    def _run_imported_scan(self, ticker: str, period: str, run_id: str) -> dict[str, Any]:
        # Placeholder normalization hook. If the external module exposes a stable
        # SignalDetectorExporter, this can be extended without touching agents.
        return {"ticker": ticker, "period": period, "run_id": run_id, "net_score": 0.0, "status": "skipped"}

    def _normalize(self, data: dict[str, Any], ticker: str, period: str, inputs_hash: str) -> April500ToolResult:
        net_score = max(0.0, min(1.0, float(data.get("net_score") or data.get("score") or 0.0)))
        return April500ToolResult(
            tool_name="april500",
            tool_family="technical",
            inputs_hash=inputs_hash,
            timeframe=period,
            status=data.get("status", "ok") if data.get("status") in {"ok", "partial", "failed", "stale", "skipped"} else "ok",
            score_delta=net_score,
            net_score=net_score,
            signals=April500Signals.model_validate(data.get("signals", {})),
            bar_confluence=data.get("bar_confluence", {}),
            support_resistance=data.get("support_resistance", {}),
            multi_timeframe_outlook=data.get("multi_timeframe_outlook", {}),
            files=data.get("files", []),
            files_persisted=bool(data.get("files_persisted", False)),
            evidence=data.get("evidence", [f"April 500 scan normalized for {ticker} {period}"]),
            counter_evidence=data.get("counter_evidence", []),
            risk_flags=data.get("risk_flags", []),
        )
