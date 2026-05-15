"""Backtest: /macro-pulse

Validates each of the 11 macro tickers against a fresh Finnhub /quote call.
Notes Finnhub-supported (VIX/DXY) and unsupported (free-tier returns c=0).
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.backtests._common import (
    fetch_backend, fetch_finnhub_quote, fetch_yf_history, finnhub_key,
    write_report, summarize, pct_delta,
)

PRICE_TOLERANCE_PCT = 1.0


def run() -> dict:
    print("backtest: /macro-pulse")
    cached = fetch_backend("/macro-pulse")
    indicators = cached.get("indicators", {})
    print(f"  validating {len(indicators)} macro indicators…")

    key = finnhub_key()
    matches = mismatches = skipped = 0
    deltas: list[dict] = []
    yf_fallback_used = 0

    with httpx.Client(timeout=15) as client:
        for tag, ind in indicators.items():
            ticker = ind.get("ticker", tag)
            cached_price = ind.get("price")
            if cached_price is None:
                skipped += 1
                continue

            fh = fetch_finnhub_quote(client, ticker, key)
            time.sleep(1.0)
            fh_price = fh.get("c")
            ref_source = "finnhub"

            # Finnhub free tier returns 0 for VIX/DXY; fall back to yfinance
            if not fh_price or fh_price == 0:
                yf_hist = fetch_yf_history([ticker], days=3)
                if ticker in yf_hist and not yf_hist[ticker].empty:
                    fh_price = float(yf_hist[ticker]["Close"].dropna().iloc[-1])
                    ref_source = "yfinance"
                    yf_fallback_used += 1
                else:
                    skipped += 1
                    continue

            drift = pct_delta(cached_price, fh_price)
            ok = drift is not None and drift <= PRICE_TOLERANCE_PCT
            deltas.append({
                "indicator": tag, "ticker": ticker,
                "cached_price": cached_price, "reference_price": fh_price,
                "reference_source": ref_source,
                "drift_pct": drift,
                "within_tolerance": ok,
            })
            if ok:
                matches += 1
            else:
                mismatches += 1

    worst = sorted(
        (d for d in deltas if not d["within_tolerance"]),
        key=lambda d: -(d.get("drift_pct") or 0),
    )[:5]

    report = {
        "price_tolerance_pct": PRICE_TOLERANCE_PCT,
        "indicators_checked": len(deltas),
        "matches": matches, "mismatches": mismatches, "skipped": skipped,
        "yfinance_fallback_count": yf_fallback_used,
        "ai_regime_cached": cached.get("ai_regime"),
        "ai_regime_score": cached.get("ai_regime_score"),
        "deltas": deltas,
        "worst_deltas": worst,
    }
    print(f"  result: {summarize(report)} · regime={cached.get('ai_regime')} · yf-fallbacks={yf_fallback_used}")
    return report


if __name__ == "__main__":
    write_report("macro_pulse", run())
