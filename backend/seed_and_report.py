"""Seed ETF price history and print a CSV report.

Strategy:
  1. Finnhub /stock/candle  — 1yr daily OHLCV, fast, 50ms/request (primary)
  2. yfinance period="max"  — full history fallback, single attempt per symbol
     Note: Alpha Vantage only has aggregated analytics, not daily price history.

Usage:
    GCP_PROJECT_ID=ttb-lang1 FINNHUB_API_KEY=<key> python seed_and_report.py
"""
import csv
import logging
import os
import sys
import time
from datetime import datetime, timezone

import httpx
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

_FINNHUB_BASE    = "https://finnhub.io/api/v1"
_FH_DELAY        = 0.12   # 120ms between requests → ~8 req/s (safe under 30/s limit)
_YF_DELAY        = 4.0    # seconds between yfinance fallback attempts


# ── Finnhub ───────────────────────────────────────────────────────────────────

def _finnhub_candles(symbol: str, from_ts: int, to_ts: int) -> list[dict]:
    """Fetch daily OHLCV from Finnhub. Returns [{date, adjusted_close, volume}]."""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return []
    time.sleep(_FH_DELAY)
    params  = {"symbol": symbol, "resolution": "D", "from": from_ts, "to": to_ts}
    headers = {"X-Finnhub-Token": api_key}
    resp = httpx.get(f"{_FINNHUB_BASE}/stock/candle", params=params, headers=headers, timeout=15)
    if resp.status_code == 429:
        logger.warning("Finnhub 429 for %s — sleeping 3s then retrying", symbol)
        time.sleep(3.0)
        resp = httpx.get(f"{_FINNHUB_BASE}/stock/candle", params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("s") != "ok" or not data.get("t"):
        return []
    return [
        {
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            "adjusted_close": float(c),
            "volume": int(v),
        }
        for ts, c, v in zip(data["t"], data["c"], data["v"])
    ]


# ── yfinance ──────────────────────────────────────────────────────────────────

def _yf_fetch(symbol: str, period: str):
    """Single yfinance attempt with browser User-Agent. No retries."""
    import requests
    import yfinance as yf
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    ticker = yf.Ticker(symbol, session=session)
    return ticker.history(period=period)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import etf_store
    from industry import _FLAT

    unique_etfs     = sorted({etf for _, etf in _FLAT.values()})
    fh_key_present  = bool(os.environ.get("FINNHUB_API_KEY"))
    to_ts           = int(time.time())
    from_ts         = to_ts - 365 * 24 * 3600  # 1 year (Finnhub free tier max)

    logger.info(
        "Seeding %d ETFs | Finnhub=%s | yfinance fallback=yes",
        len(unique_etfs), "yes" if fh_key_present else "NO KEY — fallback only",
    )

    rows: list[dict] = []

    for i, etf in enumerate(unique_etfs, 1):
        meta_before = etf_store.get_metadata(etf)
        action      = "append_delta" if meta_before is not None else "full_seed"
        logger.info("[%d/%d] %s — %s", i, len(unique_etfs), etf, action)

        source_used = "none"
        stored      = 0

        # ── 1. Finnhub (primary) ──────────────────────────────────────────────
        if fh_key_present:
            try:
                records = _finnhub_candles(etf, from_ts, to_ts)
                if records:
                    df = pd.DataFrame(records)
                    df["date"] = pd.to_datetime(df["date"])
                    df.set_index("date", inplace=True)
                    if meta_before is None:
                        stored = etf_store.store_history(etf, df, source="finnhub_seed")
                    else:
                        stored = etf_store.append_daily(etf, df, source="finnhub_delta")
                    source_used = "finnhub"
                    logger.info("✓ %s via Finnhub — %d rows", etf, stored)
                else:
                    logger.warning("Finnhub returned no data for %s", etf)
            except Exception as exc:
                logger.warning("Finnhub failed for %s: %s — trying yfinance", etf, exc)

        # ── 2. yfinance fallback ──────────────────────────────────────────────
        if source_used == "none":
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
