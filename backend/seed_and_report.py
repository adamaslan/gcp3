"""Seed ETF price history and print a CSV report.

Strategy:
  1. Alpaca SIP daily bars   — batched, split-adjusted, ~10y of history (primary)
  2. yfinance period="max"   — fallback for ETFs Alpaca has no bars for; LOCAL RUNS ONLY
     (Finnhub /stock/candle was removed: it is a paid endpoint and returns 403 on the free key.)
     Note: Alpha Vantage only has aggregated analytics, not daily price history.
     Note: Alpaca closes are split-adjusted, not dividend-adjusted; yfinance rows are both.

Usage:
    GCP_PROJECT_ID=ttb-lang1 ALPACA_API_KEY=<key> ALPACA_API_SECRET=<secret> python seed_and_report.py
"""
import csv
import logging
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd

import alpaca_md

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

ALPACA_HISTORY_DAYS = 3650  # Alpaca SIP daily bars go back roughly ten years
_YF_DELAY        = 4.0    # seconds between yfinance fallback attempts


# ── Alpaca ────────────────────────────────────────────────────────────────────

def _alpaca_history(etfs: list[str], days: int) -> dict[str, pd.DataFrame]:
    """One batched Alpaca pull. Returns {etf: DataFrame[adjusted_close, volume]} for ETFs it served."""
    if not alpaca_md.is_configured():
        logger.warning("ALPACA_API_KEY/ALPACA_API_SECRET not set — every ETF falls back to yfinance")
        return {}
    try:
        frames = alpaca_md.daily_bars_frames(etfs, days)
    except alpaca_md.AlpacaError as exc:
        alpaca_md.warn_fallback("history", etfs, exc)
        return {}
    return {
        etf: df.rename(columns={"Close": "adjusted_close", "Volume": "volume"})[["adjusted_close", "volume"]]
        for etf, df in frames.items()
    }


# ── yfinance ──────────────────────────────────────────────────────────────────

def _yf_fetch(symbol: str, period: str):
    """Single yfinance attempt. No retries.

    Deliberately passes no `session`: current yfinance rejects a
    requests.Session ("Yahoo API requires curl_cffi session") and raises
    YFDataException before any request goes out, which silently disabled the
    whole fallback leg. yfinance builds its own curl_cffi session with a
    browser User-Agent already, so the hand-rolled one bought nothing.
    """
    import yfinance as yf
    return yf.Ticker(symbol).history(period=period)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import etf_store
    from industry import _FLAT

    unique_etfs     = sorted({etf for _, etf in _FLAT.values()})
    alpaca_frames   = _alpaca_history(unique_etfs, ALPACA_HISTORY_DAYS)
    yf_allowed      = not alpaca_md.on_datacenter_host()

    logger.info(
        "Seeding %d ETFs | Alpaca served %d | yfinance fallback=%s",
        len(unique_etfs), len(alpaca_frames), "yes" if yf_allowed else "no (datacenter host)",
    )

    rows: list[dict] = []

    for i, etf in enumerate(unique_etfs, 1):
        meta_before = etf_store.get_metadata(etf)
        action      = "append_delta" if meta_before is not None else "full_seed"
        logger.info("[%d/%d] %s — %s", i, len(unique_etfs), etf, action)

        source_used = "none"
        stored      = 0

        # ── 1. Alpaca (primary) ───────────────────────────────────────────────
        df = alpaca_frames.get(etf)
        if df is not None and not df.empty:
            try:
                if meta_before is None:
                    stored = etf_store.store_history(etf, df, source="alpaca_seed")
                else:
                    stored = etf_store.append_daily(etf, df.tail(90), source="alpaca_delta")
                source_used = "alpaca"
                logger.info("✓ %s via Alpaca — %d rows", etf, stored)
            except Exception as exc:  # Firestore write errors vary; keep seeding the rest
                logger.error("store failed for %s after Alpaca fetch: %s", etf, exc)
        else:
            alpaca_md.warn_fallback("history", [etf], "no Alpaca bars")

        # ── 2. yfinance fallback ──────────────────────────────────────────────
        if source_used == "none" and yf_allowed:
            if i > 1:
                time.sleep(_YF_DELAY)
            try:
                period = "max" if meta_before is None else "3mo"
                hist   = _yf_fetch(etf, period)
                if not hist.empty:
                    hist = hist.rename(columns={"Close": "adjusted_close", "Volume": "volume"})
                    if meta_before is None:
                        stored = etf_store.store_history(etf, hist, source="yfinance_seed")
                    else:
                        stored = etf_store.append_daily(etf, hist, source="yfinance_delta")
                    source_used = "yfinance"
                    logger.info("✓ %s via yfinance fallback — %d rows", etf, stored)
                else:
                    logger.warning("yfinance also returned empty for %s", etf)
            except Exception as exc:
                logger.error("yfinance also failed for %s: %s", etf, exc)

        meta_after = etf_store.get_metadata(etf)
        rows.append({
            "symbol":      etf,
            "action":      action,
            "source":      source_used,
            "rows_stored": stored,
            "first_date":  meta_after.get("first_date", "") if meta_after else "",
            "last_date":   meta_after.get("last_date",  "") if meta_after else "",
            "total_days":  meta_after.get("total_days",  0) if meta_after else 0,
            "status":      "ok" if stored > 0 else "no_data",
        })

    # ── CSV to stdout ─────────────────────────────────────────────────────────
    fields = ["symbol", "action", "source", "rows_stored",
              "first_date", "last_date", "total_days", "status"]
    writer = csv.DictWriter(sys.stdout, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

    ok     = sum(1 for r in rows if r["status"] == "ok")
    total  = sum(r["rows_stored"] for r in rows)
    failed = [r["symbol"] for r in rows if r["status"] != "ok"]
    logger.info(
        "Done: %d/%d seeded, %d total rows | failed: %s",
        ok, len(unique_etfs), total, failed or "none",
    )


if __name__ == "__main__":
    main()
