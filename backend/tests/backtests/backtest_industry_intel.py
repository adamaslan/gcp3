"""Backtest: /industry-intel

Validates today's per-industry rankings against yfinance close-to-close moves
for the same ETF universe. /industry-intel exposes leaders/laggards by 1d %
move; we recompute each from yfinance and check ranking order + magnitudes.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.backtests._common import (
    fetch_backend, fetch_yf_history, write_report, summarize,
)

TOLERANCE_PP = 0.3  # tighter than industry-returns — this is just today's move


def run() -> dict:
    print("backtest: /industry-intel")
    cached = fetch_backend("/industry-intel")
    leaders = cached.get("leaders", []) or cached.get("rankings", [])[:10]
    laggards = cached.get("laggards", []) or cached.get("rankings", [])[-10:]

    all_rows: list[dict] = []
    for row in leaders + laggards:
        if isinstance(row, dict) and row.get("etf"):
            all_rows.append(row)

    etfs = list({r["etf"] for r in all_rows})
    print(f"  fetching yfinance for {len(etfs)} ETFs from leaders+laggards…")
    hist = fetch_yf_history(etfs, days=3)

    matches = mismatches = skipped = 0
    deltas: list[dict] = []
    for row in all_rows:
        etf = row["etf"]
        cached_pct = row.get("change_pct") or row.get("return") or row.get("pct_change")
        if cached_pct is None or etf not in hist:
            skipped += 1
            continue
        closes = hist[etf]["Close"].dropna()
        if len(closes) < 2:
            skipped += 1
            continue
        yf_pct = round((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100, 2)
        diff_pp = abs(cached_pct - yf_pct)
        entry = {
            "industry": row.get("industry") or row.get("name"),
            "etf": etf, "cached_change_pct": cached_pct, "yfinance_change_pct": yf_pct,
            "diff_pp": round(diff_pp, 3),
            "within_tolerance": diff_pp <= TOLERANCE_PP,
        }
        deltas.append(entry)
        if diff_pp <= TOLERANCE_PP:
            matches += 1
        else:
            mismatches += 1

    worst = sorted(
        (d for d in deltas if not d["within_tolerance"]),
        key=lambda d: -d["diff_pp"],
    )[:10]

    # Also check top-3 ranking agreement
    leader_etfs_cached = [r["etf"] for r in leaders[:3] if isinstance(r, dict) and r.get("etf")]
    yf_ranking = sorted(
        deltas, key=lambda d: -d["yfinance_change_pct"],
    )[:3]
    leader_etfs_yf = [d["etf"] for d in yf_ranking]
    top3_agreement = len(set(leader_etfs_cached) & set(leader_etfs_yf))

    report = {
        "tolerance_pp": TOLERANCE_PP,
        "rows_compared": len(deltas),
        "matches": matches, "mismatches": mismatches, "skipped": skipped,
        "top3_leader_overlap": top3_agreement,
        "leaders_cached_top3": leader_etfs_cached,
        "leaders_yf_top3": leader_etfs_yf,
        "worst_deltas": worst,
    }
    print(f"  result: {summarize(report)} · top3 overlap {top3_agreement}/3")
    return report


if __name__ == "__main__":
    write_report("industry_intel", run())
