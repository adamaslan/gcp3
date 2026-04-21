"""Feature Validation & Data Quality.

Range checks, cross-feature consistency, freshness, telemetry writes.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

TELEMETRY_COLLECTION = "feature_quality_issues"
STALE_THRESHOLD_SECONDS = 86_400  # 24 hours


@dataclass
class ValidationViolation:
    feature: str
    ticker: str
    rule: str
    value: Any
    severity: str  # "warning" | "error"


@dataclass
class ValidationResult:
    ticker: str
    violations: list[ValidationViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(v.severity == "error" for v in self.violations)


# Range rules: feature_name -> list of (field_path, min, max)
_RANGE_RULES: dict[str, list[tuple[str, float, float]]] = {
    "rsi": [("rsi_value", 0.0, 100.0)],
    "correlation": [("correlation", -1.0, 1.0)],
    "bollinger": [("position_pct", -2.0, 3.0), ("band_width_pct", 0.0, 100.0)],
    "volume": [("zscore", -10.0, 10.0)],
    "vix_term": [("vix_spot", 5.0, 150.0)],
    "options_sentiment": [("equity_pc_ratio", 0.1, 5.0)],
}


def validate_features(
    ticker: str,
    features: dict[str, Any],
    fetched_at: datetime | None = None,
) -> ValidationResult:
    """Run range checks and cross-feature consistency on a feature dict.

    Args:
        ticker: Stock symbol for logging context.
        features: Dict of feature_name -> feature data dict.
        fetched_at: Timestamp features were fetched (for freshness check).

    Returns:
        ValidationResult with all violations found.
    """
    result = ValidationResult(ticker=ticker)

    # Range checks
    for feature_name, rules in _RANGE_RULES.items():
        feature_data = features.get(feature_name)
        if feature_data is None or feature_data == "feature_unavailable":
            continue
        if not isinstance(feature_data, dict):
            continue
        for field_path, min_val, max_val in rules:
            val = feature_data.get(field_path)
            if val is None:
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(fval):
                result.violations.append(ValidationViolation(
                    feature=feature_name, ticker=ticker,
                    rule=f"{field_path} must be finite",
                    value=val, severity="error",
                ))
            elif not (min_val <= fval <= max_val):
                result.violations.append(ValidationViolation(
                    feature=feature_name, ticker=ticker,
                    rule=f"{field_path} out of range [{min_val}, {max_val}]",
                    value=val, severity="warning",
                ))

    # Cross-feature consistency: BB above_upper + volume z-score < -2 is suspicious
    bb = features.get("bollinger", {})
    vol = features.get("volume", {})
    if isinstance(bb, dict) and isinstance(vol, dict):
        bb_pos = bb.get("position")
        vol_z = vol.get("zscore")
        if bb_pos == "above_upper" and vol_z is not None and vol_z < -2.0:
            result.violations.append(ValidationViolation(
                feature="bollinger+volume", ticker=ticker,
                rule="BB above_upper with volume z-score < -2 is suspicious (low-volume breakout)",
                value={"bb_position": bb_pos, "volume_zscore": vol_z},
                severity="warning",
            ))

    # Freshness check
    if fetched_at is not None:
        now = datetime.now(timezone.utc)
        age_seconds = (now - fetched_at.replace(tzinfo=timezone.utc) if fetched_at.tzinfo is None
                       else now - fetched_at).total_seconds()
        if age_seconds > STALE_THRESHOLD_SECONDS:
            result.violations.append(ValidationViolation(
                feature="freshness", ticker=ticker,
                rule=f"Features older than {STALE_THRESHOLD_SECONDS}s",
                value=round(age_seconds, 0),
                severity="warning",
            ))
            logger.warning(
                "feature_staleness_alert ticker=%s age_seconds=%.0f", ticker, age_seconds
            )

    # Log violations
    for v in result.violations:
        logger.warning(
            "feature_violation ticker=%s feature=%s rule=%s value=%s severity=%s",
            v.ticker, v.feature, v.rule, v.value, v.severity,
        )

    # Write to Firestore telemetry
    if result.violations:
        _write_telemetry(ticker, result.violations)

    return result


def _write_telemetry(ticker: str, violations: list[ValidationViolation]) -> None:
    try:
        from firestore import db
        doc = {
            "ticker": ticker,
            "ts": datetime.now(timezone.utc).isoformat(),
            "violations": [
                {"feature": v.feature, "rule": v.rule, "value": str(v.value), "severity": v.severity}
                for v in violations
            ],
        }
        db.collection(TELEMETRY_COLLECTION).add(doc)
    except Exception as e:
        logger.warning("feature_telemetry_write_failed ticker=%s error=%s", ticker, e)
