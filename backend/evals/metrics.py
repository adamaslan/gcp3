"""All 9 eval metrics (Weakness #1)."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PredictionRecord:
    signal: str           # "buy","sell","hold","strong_buy","strong_sell"
    confidence: float
    forward_return_5d: float  # actual 5-day forward return
    regime: str           # "risk_on","risk_off","transitional"
    schema_valid: bool    # did output pass Pydantic without retry?
    latency_ms: float
    cost_usd: float
    input_fingerprint: str  # hash of input features for consistency check


BUY_SIGNALS = {"buy", "strong_buy"}
SELL_SIGNALS = {"sell", "strong_sell"}


def compute_hit_rate(records: list[PredictionRecord]) -> float:
    """Directional correctness vs 5-day forward return.

    A "hit" is: buy + positive return OR sell + negative return.
    Hold signals are excluded (no directional bet).
    """
    directional = [r for r in records if r.signal in BUY_SIGNALS | SELL_SIGNALS]
    if not directional:
        return float("nan")
    hits = sum(
        1 for r in directional
        if (r.signal in BUY_SIGNALS and r.forward_return_5d > 0)
        or (r.signal in SELL_SIGNALS and r.forward_return_5d < 0)
    )
    return round(hits / len(directional), 4)


def compute_sharpe(records: list[PredictionRecord], annualization: int = 252) -> float:
    """Signal-weighted Sharpe ratio (annualized, daily rebalance assumed).

    Weight = confidence for buy; -confidence for sell; 0 for hold.
    """
    weighted_returns: list[float] = []
    for r in records:
        if r.signal in BUY_SIGNALS:
            weighted_returns.append(r.confidence * r.forward_return_5d)
        elif r.signal in SELL_SIGNALS:
            weighted_returns.append(-r.confidence * r.forward_return_5d)
        else:
            weighted_returns.append(0.0)

    if len(weighted_returns) < 2:
        return float("nan")

    n = len(weighted_returns)
    mean = sum(weighted_returns) / n
    variance = sum((x - mean) ** 2 for x in weighted_returns) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return float("nan")
    return round(mean / std * math.sqrt(annualization), 4)


def compute_consistency(records: list[PredictionRecord]) -> float:
    """Flip rate on stable-input pairs (same fingerprint on consecutive days).

    Lower is better — stable inputs should produce stable outputs.
    Returns 1 - flip_rate so higher = more consistent.
    """
    by_fingerprint: dict[str, list[str]] = {}
    for r in records:
        by_fingerprint.setdefault(r.input_fingerprint, []).append(r.signal)

    pairs_total = 0
    pairs_flipped = 0
    for signals in by_fingerprint.values():
        for i in range(len(signals) - 1):
            pairs_total += 1
            if signals[i] != signals[i + 1]:
                pairs_flipped += 1

    if pairs_total == 0:
        return float("nan")
    return round(1.0 - pairs_flipped / pairs_total, 4)


def compute_calibration(records: list[PredictionRecord], n_bins: int = 10) -> float:
    """Expected Calibration Error (ECE) across n_bins confidence buckets.

    Lower is better. A perfectly calibrated model has ECE = 0.
    """
    bin_size = 1.0 / n_bins
    bins: list[list[PredictionRecord]] = [[] for _ in range(n_bins)]
    for r in records:
        if r.signal not in BUY_SIGNALS | SELL_SIGNALS:
            continue
        idx = min(int(r.confidence / bin_size), n_bins - 1)
        bins[idx].append(r)

    total = sum(len(b) for b in bins)
    if total == 0:
        return float("nan")

    ece = 0.0
    for i, bucket in enumerate(bins):
        if not bucket:
            continue
        bin_conf = (i + 0.5) * bin_size
        hit_rate = sum(
            1 for r in bucket
            if (r.signal in BUY_SIGNALS and r.forward_return_5d > 0)
            or (r.signal in SELL_SIGNALS and r.forward_return_5d < 0)
        ) / len(bucket)
        ece += (len(bucket) / total) * abs(hit_rate - bin_conf)

    return round(ece, 4)


def compute_schema_validity_rate(records: list[PredictionRecord]) -> float:
    """Fraction of outputs passing Pydantic validation without retry."""
    if not records:
        return float("nan")
    valid = sum(1 for r in records if r.schema_valid)
    return round(valid / len(records), 4)


def compute_avg_cost(records: list[PredictionRecord]) -> float:
    """Average cost per signal in USD."""
    if not records:
        return float("nan")
    return round(sum(r.cost_usd for r in records) / len(records), 8)


def compute_latency_p95(records: list[PredictionRecord]) -> float:
    """Wall-clock p95 latency in ms."""
    if not records:
        return float("nan")
    sorted_ms = sorted(r.latency_ms for r in records)
    idx = int(math.ceil(0.95 * len(sorted_ms))) - 1
    return round(sorted_ms[max(0, idx)], 1)


def compute_refusal_rate(records: list[PredictionRecord]) -> float:
    """Fraction of records with no valid signal (hold + schema_invalid)."""
    if not records:
        return float("nan")
    refused = sum(1 for r in records if not r.schema_valid)
    return round(refused / len(records), 4)


def compute_regime_stratified_accuracy(
    records: list[PredictionRecord],
) -> dict[str, float]:
    """Hit rate split by regime label."""
    regimes = set(r.regime for r in records)
    result: dict[str, float] = {}
    for regime in sorted(regimes):
        subset = [r for r in records if r.regime == regime]
        result[regime] = compute_hit_rate(subset)
    return result
