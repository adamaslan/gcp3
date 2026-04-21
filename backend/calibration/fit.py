"""Confidence calibration via Platt scaling (Weakness #2).

Nightly refit; model persisted to GCS gs://gcp3-calibration/v{N}.pkl.
"""
from __future__ import annotations

import logging
import math
import pickle
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

GCS_BUCKET = "gcp3-calibration"
N_BINS = 10


@dataclass
class CalibrationModel:
    """Platt scaling parameters: P_calibrated = sigmoid(A * raw + B)."""
    A: float
    B: float
    version: int
    n_samples: int
    ece_before: float
    ece_after: float


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def fit_calibration(rows: list[dict[str, Any]], version: int = 1) -> CalibrationModel:
    """Fit Platt scaling over prediction ledger rows.

    Args:
        rows: List of dicts with keys: confidence (float), hit (bool).
        version: Version number for GCS artifact naming.

    Returns:
        Fitted CalibrationModel.
    """
    if len(rows) < 20:
        logger.warning("calibration: insufficient rows (%d < 20), returning identity", len(rows))
        return CalibrationModel(A=1.0, B=0.0, version=version, n_samples=len(rows),
                                ece_before=float("nan"), ece_after=float("nan"))

    confs = [r["confidence"] for r in rows]
    hits = [1.0 if r["hit"] else 0.0 for r in rows]

    ece_before = _compute_ece(confs, hits)

    # Platt scaling via gradient descent (no scipy dependency)
    A, B = 1.0, 0.0
    lr = 0.01
    for _ in range(500):
        grad_A = grad_B = 0.0
        for conf, hit in zip(confs, hits):
            pred = _sigmoid(A * conf + B)
            err = pred - hit
            grad_A += err * conf
            grad_B += err
        n = len(rows)
        A -= lr * grad_A / n
        B -= lr * grad_B / n

    calibrated = [_sigmoid(A * c + B) for c in confs]
    ece_after = _compute_ece(calibrated, hits)

    model = CalibrationModel(
        A=A, B=B, version=version, n_samples=len(rows),
        ece_before=round(ece_before, 4), ece_after=round(ece_after, 4),
    )
    logger.info(
        "calibration_fit version=%d n=%d ece_before=%.4f ece_after=%.4f A=%.4f B=%.4f",
        version, len(rows), ece_before, ece_after, A, B,
    )
    _persist_to_gcs(model, version)
    return model


def apply_calibrated_confidence(raw_conf: float, model: CalibrationModel) -> float:
    """Remap raw confidence → calibrated empirical hit rate."""
    calibrated = _sigmoid(model.A * raw_conf + model.B)
    return round(max(0.001, min(0.999, calibrated)), 4)


def adjust_confidence_structurally(
    raw: float,
    alignment_score: float,
    evidence_count: int,
    freshness_seconds: float,
) -> float:
    """Pre-calibration confidence caps based on signal quality.

    Args:
        raw: Raw model confidence (0–1).
        alignment_score: Fraction of timeframes agreeing (0–1).
        evidence_count: Number of evidence items provided.
        freshness_seconds: Age of freshest input feature in seconds.

    Returns:
        Adjusted confidence, capped if signal quality is poor.
    """
    adjusted = raw

    # Low alignment caps confidence
    if alignment_score < 0.5:
        adjusted = min(adjusted, 0.55)
    elif alignment_score < 0.67:
        adjusted = min(adjusted, 0.70)

    # Too few evidence items
    if evidence_count < 2:
        adjusted = min(adjusted, 0.50)

    # Stale data (>24h)
    STALE_SECONDS = 86_400
    if freshness_seconds > STALE_SECONDS:
        adjusted = min(adjusted, 0.45)
        logger.warning(
            "confidence_capped_for_stale_data freshness_seconds=%.0f", freshness_seconds
        )

    # Never allow exactly 0 or 1
    adjusted = max(0.001, min(0.999, adjusted))
    return round(adjusted, 4)


def _compute_ece(confs: list[float], hits: list[float]) -> float:
    bin_size = 1.0 / N_BINS
    ece = 0.0
    n = len(confs)
    for i in range(N_BINS):
        low, high = i * bin_size, (i + 1) * bin_size
        bucket = [(c, h) for c, h in zip(confs, hits) if low <= c < high]
        if not bucket:
            continue
        mean_conf = sum(c for c, _ in bucket) / len(bucket)
        mean_hit = sum(h for _, h in bucket) / len(bucket)
        ece += (len(bucket) / n) * abs(mean_hit - mean_conf)
    return round(ece, 4)


def _persist_to_gcs(model: CalibrationModel, version: int) -> None:
    try:
        from google.cloud import storage  # type: ignore
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(f"v{version}.pkl")
        blob.upload_from_string(pickle.dumps(model))
        logger.info("calibration_model_saved gcs=gs://%s/v%d.pkl", GCS_BUCKET, version)
    except Exception as e:
        logger.warning("calibration_gcs_persist_failed error=%s", e)


def load_from_gcs(version: int) -> CalibrationModel | None:
    """Load a previously persisted calibration model from GCS."""
    try:
        from google.cloud import storage  # type: ignore
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(f"v{version}.pkl")
        data = blob.download_as_bytes()
        return pickle.loads(data)
    except Exception as e:
        logger.warning("calibration_gcs_load_failed version=%d error=%s", version, e)
        return None
