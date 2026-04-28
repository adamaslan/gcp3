"""Rule-based signal variant mirroring utils.signals.ai_signal logic for eval comparison."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from evals.metrics import PredictionRecord


class BaselineRuleVariant:
    """Wraps the deterministic rule-based signal from screener.py as a SignalVariant."""

    name = "baseline_rule"
    prompt_version = "n/a"
    model_id = "rule_based"

    def predict(self, ticker: str, as_of: date, features: dict[str, Any]) -> PredictionRecord:
        """Produce a PredictionRecord using the rule-based momentum signal.

        Args:
            ticker: Stock symbol.
            as_of: Date of prediction (for ledger).
            features: Dict containing at minimum: change_pct, price, high, low,
                      forward_return_5d, regime.

        Returns:
            PredictionRecord with schema_valid=True (rule always produces valid output).
        """
        signal = _rule_signal(features)
        confidence = _rule_confidence(signal, features)
        fingerprint = hashlib.sha256(
            json.dumps({k: features.get(k) for k in sorted(features)}, default=str).encode()
        ).hexdigest()[:16]

        return PredictionRecord(
            signal=signal,
            confidence=confidence,
            forward_return_5d=float(features.get("forward_return_5d", 0.0)),
            regime=str(features.get("regime", "unknown")),
            schema_valid=True,
            latency_ms=0.1,
            cost_usd=0.0,
            input_fingerprint=fingerprint,
        )


def _rule_signal(features: dict[str, Any]) -> str:
    pct = features.get("change_pct", 0)
    price = features.get("price", 0)
    low = features.get("low", price)
    high = features.get("high", price)
    intraday_range = high - low
    position_in_range = (price - low) / intraday_range if intraday_range > 0 else 0.5

    if pct > 3 and position_in_range > 0.75:
        return "strong_buy"
    if pct > 1.5 or (pct > 0.5 and position_in_range > 0.7):
        return "buy"
    if pct < -3 and position_in_range < 0.25:
        return "strong_sell"
    if pct < -1.5 or (pct < -0.5 and position_in_range < 0.3):
        return "sell"
    return "hold"


def _rule_confidence(signal: str, features: dict[str, Any]) -> float:
    pct = abs(features.get("change_pct", 0))
    if signal in ("strong_buy", "strong_sell"):
        return min(0.85, 0.60 + pct * 0.05)
    if signal in ("buy", "sell"):
        return min(0.70, 0.45 + pct * 0.05)
    return 0.30
