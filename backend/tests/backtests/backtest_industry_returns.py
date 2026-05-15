"""Backtest: /industry-returns

Validates the cached 1d/1w/1m returns for each of the 54 industry ETFs by
recomputing them from fresh yfinance adjusted-close data over the last
~30 trading days. A mismatch >0.5pp on any period is flagged.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # backend/

from tests.backtests._common import (
    fetch_backend, fetch_yf_history, pct_delta, write_report, summarize,
)

TOLERANCE_PP = 0.5  # absolute percentage-point tolerance on return values


def _compute_return(prices, days_back: int) -> float | None:
    """% return from prices[-1-days_back] to prices[-1]."""
    if len(prices) < days_back + 1:
        return None
    end = prices.iloc[-1]
    start = prices.iloc[-1 - days_back]
    if start == 0:
        return None
    return round((end - start) / start * 100, 2)


def run() -> dict:
    print("backtest: /industry-returns")
    cached = fetch_backend("/industry-returns")
    leaders_1d = cached.get("leaders", {}).get("1d", [])
    leaders_1m = cached.get("leaders", {}).get("1m", [])

    # Build {industry: etf, cached_1d, cached_1m} index from leaders + laggards
    index: dict[str, dict] = {}
    for period in ("1d", "1w", "1m"):
        for bucket in ("leaders", "laggards"):
            for row in cached.get(bucket, {}).get(period, []):
                ind = row.get("industry")
                if not ind:
                    continue
                index.setdefault(ind, {"etf": row.get("etf"), "industries": ind})
                index[ind][f"cached_{period}"] = row.get("return")

    etfs = [v["etf"] for v in index.values() if v.get("etf")]
    print(f"  fetching yfinance history for {len(etfs)} ETFs…")
    hist = fetch_yf_history(etfs, days=35)

    matches = mismatches = skipped = 0
    deltas: list[dict] = []

    for ind, row in index.items():
        etf = row.get("etf")
        if etf not in hist:
            skipped += 1
            continue
        closes = hist[etf]["Close"].dropna()
        if closes.empty:
            skipped += 1
            continue

        for period, days_back in (("1d", 1), ("1w", 5), ("1m", 21)):
            cached_val = row.get(f"cached_{period}")
            yf_val = _compute_return(closes, days_back)
            if cached_val is None or yf_val is None:
                continue
            diff_pp = abs(cached_val - yf_val)
            entry = {
                "industry": ind, "etf": etf, "period": period,
                "cached": cached_val, "yfinance": yf_val,
                "diff_pp": round(diff_pp, 3),
                "within_tolerance": diff_pp <= TOLERANCE_PP,
            }
            deltas.append(entry)
            if diff_pp <= TOLERANCE_PP:
                matches += 1
            else:
                mismatches += 1

    # Surface the worst 10 deltas
    worst = sorted(
        (d for d in deltas if not d["within_tolerance"]),
        key=lambda d: -d["diff_pp"],
    )[:10]

    report = {
        "tolerance_pp": TOLERANCE_PP,
        "etfs_checked": len(etfs),
        "etfs_with_yf_data": len(hist),
        "comparisons": len(deltas),
        "matches": matches,
        "mismatches": mismatches,
        "skipped": skipped,
        "worst_deltas": worst,
        "leaders_1d_cached": [{"industry": l["industry"], "return": l["return"]} for l in leaders_1d[:5]],
        "leaders_1m_cached": [{"industry": l["industry"], "return": l["return"]} for l in leaders_1m[:5]],
    }
    print(f"  result: {summarize(report)}")
    if worst:
        print("  worst deltas:")
        for w in worst[:3]:
            print(f"    {w['etf']} {w['period']}: cached={w['cached']:+.2f}% yf={w['yfinance']:+.2f}% Δ={w['diff_pp']:.2f}pp")
    return report


if __name__ == "__main__":
    write_report("industry_returns", run())
