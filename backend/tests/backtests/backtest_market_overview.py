"""Backtest: /market-overview

Cross-source sanity check. /market-overview pulls indices + sentiment + brief.
Validate the headline index moves (SPY, QQQ, DIA, IWM) against yfinance.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.backtests._common import (
    fetch_backend, fetch_yf_history, write_report, summarize,
)

CHANGE_TOLERANCE_PP = 0.3

INDICES = ["SPY", "QQQ", "DIA", "IWM"]


def _walk_for_index(obj, sym: str) -> dict | None:
    """Find the first dict in nested obj that has obj['symbol'] == sym or obj.get('ticker') == sym."""
    if isinstance(obj, dict):
        if obj.get("symbol") == sym or obj.get("ticker") == sym:
            return obj
        for v in obj.values():
            found = _walk_for_index(v, sym)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _walk_for_index(item, sym)
            if found:
                return found
    return None


def run() -> dict:
    print("backtest: /market-overview")
    cached = fetch_backend("/market-overview")

    print(f"  fetching yfinance for {len(INDICES)} indices…")
    hist = fetch_yf_history(INDICES, days=3)

    matches = mismatches = skipped = 0
    deltas: list[dict] = []

    for sym in INDICES:
        ind = _walk_for_index(cached, sym)
        if not ind:
            deltas.append({"symbol": sym, "status": "not_in_payload"})
            skipped += 1
            continue
        cached_change = ind.get("change_pct") or ind.get("pct_change") or ind.get("dp")
        cached_price = ind.get("price") or ind.get("c")
        if cached_change is None or sym not in hist:
            skipped += 1
            continue
        closes = hist[sym]["Close"].dropna()
        if len(closes) < 2:
            skipped += 1
            continue
        yf_change = round((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100, 2)
        diff_pp = abs(cached_change - yf_change)
        ok = diff_pp <= CHANGE_TOLERANCE_PP
        deltas.append({
            "symbol": sym,
            "cached_price": cached_price,
            "cached_change_pct": cached_change,
            "yf_change_pct": yf_change,
            "diff_pp": round(diff_pp, 3),
            "within_tolerance": ok,
        })
        if ok: matches += 1
        else: mismatches += 1

    report = {
        "change_tolerance_pp": CHANGE_TOLERANCE_PP,
        "indices_checked": len(INDICES),
        "matches": matches, "mismatches": mismatches, "skipped": skipped,
        "sentiment_cached": cached.get("sentiment"),
        "sections_included": cached.get("sections_included"),
        "deltas": deltas,
    }
    print(f"  result: {summarize(report)}")
    return report


if __name__ == "__main__":
    write_report("market_overview", run())
