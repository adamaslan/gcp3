"""Eval harness with CI gating (Weakness #1)."""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol, runtime_checkable

from evals.metrics import (
    PredictionRecord,
    compute_avg_cost,
    compute_calibration,
    compute_consistency,
    compute_hit_rate,
    compute_latency_p95,
    compute_refusal_rate,
    compute_regime_stratified_accuracy,
    compute_schema_validity_rate,
    compute_sharpe,
)

logger = logging.getLogger(__name__)

# CI regression thresholds (Tier 1 = gating)
REGRESSION_THRESHOLDS = {
    "hit_rate": -0.015,       # -1.5 pp
    "sharpe": -0.10,
    "consistency": -0.03,     # -3 pp
    "schema_validity_rate": -0.005,  # -0.5 pp
}


@runtime_checkable
class SignalVariant(Protocol):
    name: str
    prompt_version: str
    model_id: str

    def predict(self, ticker: str, as_of: date, features: dict[str, Any]) -> PredictionRecord:
        ...


@dataclass
class EvalRunResult:
    variant_name: str
    prompt_version: str
    model_id: str
    run_at: str
    n_records: int
    hit_rate: float
    sharpe: float
    consistency: float
    calibration_ece: float
    schema_validity_rate: float
    avg_cost_usd: float
    latency_p95_ms: float
    refusal_rate: float
    regime_accuracy: dict[str, float] = field(default_factory=dict)


@dataclass
class EvalHarness:
    """Run eval variants against historical records and gate deployment."""

    records: list[PredictionRecord]

    def run_variant(self, variant: SignalVariant) -> EvalRunResult:
        """Score a single variant against self.records."""
        return EvalRunResult(
            variant_name=variant.name,
            prompt_version=variant.prompt_version,
            model_id=variant.model_id,
            run_at=datetime.now(timezone.utc).isoformat(),
            n_records=len(self.records),
            hit_rate=compute_hit_rate(self.records),
            sharpe=compute_sharpe(self.records),
            consistency=compute_consistency(self.records),
            calibration_ece=compute_calibration(self.records),
            schema_validity_rate=compute_schema_validity_rate(self.records),
            avg_cost_usd=compute_avg_cost(self.records),
            latency_p95_ms=compute_latency_p95(self.records),
            refusal_rate=compute_refusal_rate(self.records),
            regime_accuracy=compute_regime_stratified_accuracy(self.records),
        )

    def ci_gate(self, baseline: EvalRunResult, candidate: EvalRunResult) -> bool:
        """Return True if candidate passes CI gate (no Tier-1 regressions).

        Exits with code 1 if any gating metric regresses beyond threshold.
        """
        regressions: list[str] = []
        metric_map = {
            "hit_rate": (baseline.hit_rate, candidate.hit_rate),
            "sharpe": (baseline.sharpe, candidate.sharpe),
            "consistency": (baseline.consistency, candidate.consistency),
            "schema_validity_rate": (
                baseline.schema_validity_rate,
                candidate.schema_validity_rate,
            ),
        }
        for metric, (base_val, cand_val) in metric_map.items():
            import math
            if math.isnan(base_val) or math.isnan(cand_val):
                continue
            delta = cand_val - base_val
            threshold = REGRESSION_THRESHOLDS[metric]
            if delta < threshold:
                regressions.append(
                    f"{metric}: baseline={base_val:.4f} candidate={cand_val:.4f} "
                    f"delta={delta:+.4f} (threshold {threshold:+.4f})"
                )

        if regressions:
            logger.error("CI_GATE_FAILED regressions=%s", regressions)
            self.print_report([baseline, candidate])
            sys.exit(1)

        logger.info("CI_GATE_PASSED candidate=%s", candidate.variant_name)
        return True

    def print_report(self, results: list[EvalRunResult]) -> None:
        """Print a human-readable comparison table to stdout."""
        header = f"{'Variant':<30} {'HitRate':>8} {'Sharpe':>8} {'Consist':>8} {'ECE':>8} {'SchemaOK':>9} {'AvgCost':>10} {'P95ms':>8}"
        print(header)
        print("-" * len(header))
        for r in results:
            print(
                f"{r.variant_name:<30} "
                f"{r.hit_rate:>8.4f} "
                f"{r.sharpe:>8.4f} "
                f"{r.consistency:>8.4f} "
                f"{r.calibration_ece:>8.4f} "
                f"{r.schema_validity_rate:>9.4f} "
                f"{r.avg_cost_usd:>10.8f} "
                f"{r.latency_p95_ms:>8.1f}"
            )
        print()
        for r in results:
            if r.regime_accuracy:
                print(f"  {r.variant_name} regime accuracy: {r.regime_accuracy}")
