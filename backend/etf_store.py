"""Permanent Firestore storage for ETF price history.

Stores full history once; daily runs append only new trading days.
Feeds industry_returns.py with multi-period return calculations
without any API calls after the initial seed.

Firestore layout:
    etf_history/{SYMBOL}          — metadata + embedded prices (≤2000 rows)
    etf_history/{SYMBOL}/years/{YYYY} — yearly chunks when >2000 rows
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from firestore import db as _db

logger = logging.getLogger(__name__)

_COLLECTION = "etf_history"
_MAX_EMBEDDED_RECORDS = 2000  # switch to yearly sub-docs above this row count
_FIRESTORE_BATCH_MAX_OPS = 450  # stay under Firestore's 500-op batch limit
_PERIOD_DAYS_MAP = {
    "1d":  1,  "3d":  3,
    "1w":  7,  "2w": 14,  "3w": 21,
    "1m": 30,  "3m": 90,  "6m": 180,
    "ytd": None,          # calculated separately
    "1y": 365, "2y": 730, "5y": 1825, "10y": 3650,
}


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def store_history(symbol: str, df: pd.DataFrame, source: str = "yfinance") -> int:
    """Store full price history. Call once per ETF; use append_daily after that.

    Args:
        symbol: ETF ticker (e.g. 'IGV').
        df: DataFrame with 'adjusted_close' and 'volume', date-indexed.
        source: Provenance tag.

    Returns:
        Number of rows stored.
    """
    symbol = symbol.upper()
    if df.empty:
        return 0

    records = _to_records(df)
    now = datetime.now(tz=timezone.utc).isoformat()
    dates = [r["date"] for r in records]
    meta = {
        "symbol": symbol, "source": source,
        "last_updated": now,
        "first_date": min(dates), "last_date": max(dates),
        "total_days": len(records),
    }

    doc = _db().collection(_COLLECTION).document(symbol)

    if len(records) <= _MAX_EMBEDDED_RECORDS:
        doc.set({**meta, "storage_mode": "embedded", "prices": records})
    else:
        doc.set({**meta, "storage_mode": "chunked"})
        batch = _db().batch()
        ops = 0
        for year, recs in _by_year(records).items():
            yr_ref = doc.collection("years").document(year)
            batch.set(yr_ref, {"year": year, "prices": recs})
            ops += 1
            if ops >= _FIRESTORE_BATCH_MAX_OPS:
                batch.commit()
                batch = _db().batch()
                ops = 0
        if ops:
            batch.commit()

    logger.info("Stored %d days for %s (%s–%s)", len(records), symbol, meta["first_date"], meta["last_date"])
    return len(records)


def append_daily(symbol: str, df: pd.DataFrame, source: str = "finnhub") -> int:
    """Append only rows newer than the last stored date.

    Args:
        symbol: ETF ticker.
        df: DataFrame with new data (may overlap stored data).
        source: Provenance tag.

    Returns:
        Number of new rows appended (0 if already current).
    """
    symbol = symbol.upper()
    if df.empty:
        return 0

    meta = get_metadata(symbol)
    if meta is None:
        return store_history(symbol, df, source)

    new_records = [r for r in _to_records(df) if r["date"] > meta["last_date"]]
    if not new_records:
        return 0

    from google.cloud.firestore_v1 import ArrayUnion
    doc = _db().collection(_COLLECTION).document(symbol)
    now = datetime.now(tz=timezone.utc).isoformat()
    new_last = max(r["date"] for r in new_records)

    if meta.get("storage_mode") == "chunked":
        for year, recs in _by_year(new_records).items():
            yr_ref = doc.collection("years").document(year)
            if yr_ref.get().exists:
                yr_ref.update({"prices": ArrayUnion(recs)})
            else:
                yr_ref.set({"year": year, "prices": recs})
    else:
        doc.update({"prices": ArrayUnion(new_records)})

    doc.update({
        "last_date": new_last,
        "last_updated": now,
        "total_days": meta["total_days"] + len(new_records),
        "source": source,
    })

    logger.info("Appended %d new days for %s", len(new_records), symbol)
    return len(new_records)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def load_history(symbol: str) -> Optional[pd.DataFrame]:
    """Load full stored price history as a DataFrame (newest-first).

    Returns None if no data stored yet.
    """
    symbol = symbol.upper()
    doc = _db().collection(_COLLECTION).document(symbol)
    snap = doc.get()
    if not snap.exists:
        return None

    data = snap.to_dict()
    if data.get("storage_mode") == "chunked":
        records = []
        for yr in doc.collection("years").stream():
            records.extend(yr.to_dict().get("prices", []))
    else:
        records = data.get("prices", [])

    if not records:
        return None

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(ascending=False, inplace=True)
    return df


def get_metadata(symbol: str) -> Optional[dict]:
    """Return metadata dict (no prices) or None if not stored."""
    symbol = symbol.upper()
    snap = _db().collection(_COLLECTION).document(symbol).get()
    if not snap.exists:
        return None
    d = snap.to_dict()
    return {k: d[k] for k in ("symbol", "source", "last_updated", "first_date",
                               "last_date", "total_days", "storage_mode") if k in d}


def compute_returns(symbol: str) -> Optional[dict]:
    """Calculate multi-period % returns from stored history.

    Returns dict keyed by period string (e.g. '1m': 4.2) or None.
    """
    df = load_history(symbol)
    if df is None or df.empty or "adjusted_close" not in df.columns:
        return None

    closes = df["adjusted_close"].dropna()
    if len(closes) < 2:
        return None

    latest = closes.iloc[0]
    today = closes.index[0]
    returns: dict[str, Optional[float]] = {}

    for period, days in _PERIOD_DAYS_MAP.items():
        if days is None:
            continue  # ytd handled below
        cutoff = today - pd.Timedelta(days=days)
        past = closes[closes.index <= cutoff]
        if past.empty:
            returns[period] = None
        else:
            base = past.iloc[0]
            returns[period] = round((latest / base - 1) * 100, 2) if base else None

    # Year-to-date: compare to last close of prior year
    ytd_cutoff = pd.Timestamp(today.year, 1, 1, tzinfo=today.tzinfo if today.tzinfo else None)
    ytd_past = closes[closes.index < ytd_cutoff]
    returns["ytd"] = (
        round((latest / ytd_past.iloc[0] - 1) * 100, 2) if not ytd_past.empty else None
    )

    # 52-week high/low
    yr = closes[closes.index >= today - pd.Timedelta(days=365)]
    returns["52w_high"] = round(float(yr.max()), 2) if not yr.empty else None
    returns["52w_low"] = round(float(yr.min()), 2) if not yr.empty else None

    return returns


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------

def _to_records(df: pd.DataFrame) -> list[dict]:
    out = []
    for idx, row in df.iterrows():
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        out.append({
            "date": date_str,
            "adjusted_close": float(row.get("adjusted_close", row.get("Close", 0))),
            "volume": int(row.get("volume", row.get("Volume", 0))),
        })
    return out


def _by_year(records: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list] = {}
    for r in records:
        yr = r["date"][:4]
        out.setdefault(yr, []).append(r)
    return out
