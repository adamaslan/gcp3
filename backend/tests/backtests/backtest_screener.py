"""Backtest: /screener

Validates each cached quote (price, change_pct) against a fresh Finnhub
/quote pull. Tolerance is wider because of intraday lag: the cache is
~15 min stale relative to live, so we expect small price drift but the
change_pct from prev_close should still match.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.backtests._common import (
    fetch_backend, fetch_finnhub_quote, finnhub_key, write_report, summarize, pct_delta,
)

PRICE_TOLERANCE_PCT = 1.5  # intraday drift acceptable
CHANGE_PCT_TOLERANCE_PP = 0.5  # prev-close based, should be tight


def run() -> dict:
    print("backtest: /screener")
    cached = fetch_backend("/screener")
    quotes_raw = cached.get("quotes") or {}
    if isinstance(quotes_raw, dict):
        quotes = list(quotes_raw.values())
    else:
        quotes = list(quotes_raw)
    if not quotes:
        quotes = (cached.get("gainers") or []) + (cached.get("losers") or [])

    print(f"  validating {len(quotes)} cached quotes against Finnhub /quote…")
    key = finnhub_key()
    matches = mismatches = skipped = 0
    deltas: list[dict] = []

    with httpx.Client(timeout=15) as client:
        for q in quotes[:50]:  # cap to 50 to stay under Finnhub free-tier rate
            symbol = q.get("symbol")
            cached_price = q.get("price")
            cached_change_pct = q.get("change_pct")
            if not symbol or cached_price is None:
                skipped += 1
                continue
            fh = fetch_finnhub_quote(client, symbol, key)
            time.sleep(1.0)  # respect Finnhub 60/min free tier
            fh_price = fh.get("c")
            fh_change_pct = fh.get("dp")
            if not fh_price or fh_price == 0:
                skipped += 1
                continue

            price_drift_pct = pct_delta(cached_price, fh_price)
            change_diff_pp = (
                abs(cached_change_pct - fh_change_pct)
                if cached_change_pct is not None and fh_change_pct is not None
                else None
            )

            price_ok = price_drift_pct is not None and price_drift_pct <= PRICE_TOLERANCE_PCT
            change_ok = change_diff_pp is None or change_diff_pp <= CHANGE_PCT_TOLERANCE_PP

            entry = {
                "symbol": symbol,
                "cached_price": cached_price, "finnhub_price": fh_price,
                "price_drift_pct": price_drift_pct,
                "cached_change_pct": cached_change_pct, "finnhub_change_pct": fh_change_pct,
                "change_diff_pp": round(change_diff_pp, 3) if change_diff_pp is not None else None,
                "price_within_tolerance": price_ok,
                "change_within_tolerance": change_ok,
            }
            deltas.append(entry)
            if price_ok and change_ok:
                matches += 1
            else:
                mismatches += 1

    worst = sorted(
        (d for d in deltas if not (d["price_within_tolerance"] and d["change_within_tolerance"])),
        key=lambda d: -(d.get("price_drift_pct") or 0),
    )[:10]

    report = {
        "price_tolerance_pct": PRICE_TOLERANCE_PCT,
        "change_tolerance_pp": CHANGE_PCT_TOLERANCE_PP,
        "quotes_checked": len(deltas),
        "matches": matches, "mismatches": mismatches, "skipped": skipped,
        "breadth_pct_cached": cached.get("breadth_pct"),
        "total_screened_cached": cached.get("total_screened"),
        "worst_deltas": worst,
    }
    print(f"  result: {summarize(report)}")
    return report


if __name__ == "__main__":
    write_report("screener", run())
