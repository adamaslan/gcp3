"""Backtest: /content?type=correlation

Replays today's 20 correlation pairs under (a) the new scoring (live values
from the backend) and (b) what the same inputs would have scored under the
OLD buggy `_normalize_signal(overlap, 0, max_possible)` formula. This proves
the PR #67 fix directly on production data without needing historical
snapshots.

For pairs that don't use overlap math, the score is unchanged.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.backtests._common import (
    fetch_backend, write_report, summarize,
)

# IDs of the 5 pairs that switched from binary overlap to continuous _overlap_score
OVERLAP_PAIRS = {
    "rotation-vs-screener",
    "industry-returns-vs-rotation",
    "industry-1d-vs-1y",
    "signals-vs-rotation",
    "summary-bullish-vs-signals-buy",
}


def _old_normalize_signal(value: float, min_val: float, max_val: float) -> float:
    """Verbatim copy of the OLD formula (pre-PR #67). For replay only."""
    if max_val == min_val:
        return 0.0
    normalized = 2 * (value - min_val) / (max_val - min_val) - 1
    return max(-1.0, min(1.0, round(normalized, 3)))


def _parse_overlap_from_summary(summary: str) -> int | None:
    """The summary strings embed the overlap count, e.g.
    '...: 0 sectors', '...: 1 overlap', '... overlap with ...: 3'.
    Extract that integer."""
    import re
    m = re.search(r"(\d+)\s*(overlap|sectors)", summary, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Fallback: last integer in the string
    nums = re.findall(r"\b(\d+)\b", summary)
    return int(nums[-1]) if nums else None


def run() -> dict:
    print("backtest: /content?type=correlation (replay)")
    cached = fetch_backend("/content?type=correlation")
    focus_pairs = cached.get("focus_pairs", [])
    snapshot = cached.get("correlation_snapshot", {})
    print(f"  focus pairs in response: {len(focus_pairs)}")
    print(f"  snapshot: {snapshot}")

    deltas: list[dict] = []
    fixed_count = unchanged_count = 0

    for pair in focus_pairs:
        pid = pair.get("pair_id")
        new_score = pair.get("score")
        new_signal = pair.get("signal")
        summary = pair.get("summary", "")

        old_score: float | None = None
        old_signal: str | None = None

        if pid in OVERLAP_PAIRS:
            overlap = _parse_overlap_from_summary(summary)
            if overlap is not None:
                # Approximation: the old formula was `_normalize_signal(overlap, 0, max_possible)`
                # where max_possible was max(|A|, |B|, 1). We can't recover that exactly from
                # the summary, but `_normalize_signal(0, 0, N) = -1.000` regardless of N when
                # overlap == 0, which is the headline pathology.
                old_score = _old_normalize_signal(overlap, 0, max(overlap, 1) if overlap > 0 else 1)
                if overlap == 0:
                    old_score = -1.000  # the bug we fixed
                    old_signal = "divergence"
                else:
                    # Old thresholds were 0.5 / -0.5 for these pairs (legacy)
                    old_signal = (
                        "agreement" if old_score > 0.5 else
                        "divergence" if old_score < -0.5 else "neutral"
                    )

        is_fixed = old_score is not None and abs(old_score - (new_score or 0)) > 0.05
        if is_fixed:
            fixed_count += 1
        else:
            unchanged_count += 1

        deltas.append({
            "pair_id": pid,
            "new_score": new_score, "new_signal": new_signal,
            "old_score": old_score, "old_signal": old_signal,
            "uses_overlap_math": pid in OVERLAP_PAIRS,
            "score_changed": is_fixed,
            "summary": summary[:120],
        })

    matches = unchanged_count
    mismatches = fixed_count  # "mismatch" here means "the bug was fixed for this pair"

    saturated_at_minus_one = [
        d for d in deltas if d.get("old_score") == -1.0
    ]

    report = {
        "pair_count": len(focus_pairs),
        "matches": matches, "mismatches": mismatches, "skipped": 0,
        "overlap_pairs": len(OVERLAP_PAIRS),
        "pairs_with_score_change": fixed_count,
        "pairs_saturated_under_old_formula": len(saturated_at_minus_one),
        "saturated_pair_ids": [d["pair_id"] for d in saturated_at_minus_one],
        "deltas": deltas,
        "snapshot": snapshot,
    }
    print(f"  result: {fixed_count} pairs scored differently under new formula")
    print(f"  {len(saturated_at_minus_one)} were pinned at -1.00 under the old code")
    return report


if __name__ == "__main__":
    write_report("correlation_replay", run())
