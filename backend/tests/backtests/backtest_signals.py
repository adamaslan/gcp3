"""Backtest: /signals

Validates the cached BUY/HOLD/SELL counts and ranked list. Strategy:
take the top-10 ranked symbols, fetch ~60 days of yfinance history,
recompute a simple momentum proxy (10d vs 30d return), and check whether
BUYs have positive momentum, SELLs negative. We're NOT trying to perfectly
replicate the production signal stack (that's RSI+MACD+breadth+more) —
just sanity-check that the direction is plausible against fresh history.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.backtests._common import (
    fetch_backend, fetch_yf_history, write_report, summarize,
)


def _momentum_pct(closes, short: int = 10, long_: int = 30) -> float | None:
    """Short-window vs long-window return spread, % points."""
    if len(closes) < long_ + 1:
        return None
    short_ret = (closes.iloc[-1] - closes.iloc[-short - 1]) / closes.iloc[-short - 1] * 100
    long_ret = (closes.iloc[-1] - closes.iloc[-long_ - 1]) / closes.iloc[-long_ - 1] * 100
    return round(short_ret - long_ret, 2)


def run() -> dict:
    print("backtest: /signals")
    cached = fetch_backend("/signals")
    summary = cached.get("signal_summary", {})
    buys = cached.get("buys", [])
    sells = cached.get("sells", [])
    ranked = cached.get("ranked", [])

    sample = (buys[:15] + sells[:5])
    etfs = [r.get("symbol") or r.get("ticker") for r in sample if r.get("symbol") or r.get("ticker")]
    etfs = list({e for e in etfs if e})
    print(f"  fetching yfinance for {len(etfs)} BUY/SELL symbols…")
    hist = fetch_yf_history(etfs, days=45)

    buy_correct = buy_incorrect = sell_correct = sell_incorrect = skipped = 0
    deltas: list[dict] = []

    for r in sample:
        sym = r.get("symbol") or r.get("ticker") or r.get("etf")
        signal = (r.get("signal") or r.get("ai_action") or r.get("direction") or "").lower()
        if not sym or sym not in hist:
            skipped += 1
            continue
        mom = _momentum_pct(hist[sym]["Close"].dropna())
        if mom is None:
            skipped += 1
            continue

        if signal == "buy":
            ok = mom > 0
            if ok: buy_correct += 1
            else: buy_incorrect += 1
        elif signal == "sell":
            ok = mom < 0
            if ok: sell_correct += 1
            else: sell_incorrect += 1
        else:
            skipped += 1
            continue

        deltas.append({
            "symbol": sym, "signal": signal, "momentum_pp": mom,
            "direction_matches": ok,
        })

    matches = buy_correct + sell_correct
    mismatches = buy_incorrect + sell_incorrect

    # Sanity check counts on the summary
    counts_sane = (
        summary.get("total_signals", 0)
        >= summary.get("buy_count", 0) + summary.get("sell_count", 0) + summary.get("hold_count", 0)
    )

    report = {
        "signal_summary_cached": summary,
        "buy_count": summary.get("buy_count"),
        "sell_count": summary.get("sell_count"),
        "hold_count": summary.get("hold_count"),
        "total_signals": summary.get("total_signals"),
        "counts_consistent": counts_sane,
        "samples_checked": len(deltas),
        "matches": matches, "mismatches": mismatches, "skipped": skipped,
        "buy_direction_accuracy": (
            round(buy_correct / max(buy_correct + buy_incorrect, 1) * 100, 1)
        ),
        "sell_direction_accuracy": (
            round(sell_correct / max(sell_correct + sell_incorrect, 1) * 100, 1)
        ),
        "samples": deltas[:20],
    }
    print(f"  result: {summarize(report)} · BUY direction {report['buy_direction_accuracy']}% · SELL {report['sell_direction_accuracy']}%")
    return report


if __name__ == "__main__":
    write_report("signals", run())
