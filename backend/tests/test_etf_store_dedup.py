"""Test append_daily date deduplication (PR follow-up to backtest 2026-05-15).

Locks the fix preventing duplicate-date rows in etf_history when two sources
(finnhub_delta / yfinance / finnhub_seed) emit the same date with different
prices — that was the silent corruption mode behind the HACK 1m -9.27%
divergence.
"""
from unittest.mock import MagicMock, patch

import pandas as pd

import etf_store


def _df(rows: list[tuple[str, float, int]]) -> pd.DataFrame:
    """Build a DataFrame yfinance/finnhub-style: date-indexed, Close + Volume cols."""
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {"adjusted_close": [r[1] for r in rows], "volume": [r[2] for r in rows]},
        index=idx,
    )


def test_append_daily_skips_duplicate_date_with_different_price():
    """Same date, different price → must NOT be appended (prevents dual-row corruption)."""
    fake_doc = MagicMock()
    fake_doc.exists = True
    fake_doc.to_dict.return_value = {
        "symbol": "TEST",
        "last_date": "2026-05-13",
        "total_days": 1,
        "storage_mode": "embedded",
        "prices": [{"date": "2026-05-13", "adjusted_close": 100.0, "volume": 1000}],
    }
    fake_ref = MagicMock()
    fake_ref.get.return_value = fake_doc
    fake_collection = MagicMock()
    fake_collection.document.return_value = fake_ref

    new_df = _df([
        ("2026-05-13", 99999.0, 9999),  # SAME date, garbage price — must be rejected
        ("2026-05-14", 105.0, 2000),     # new date — must be appended
    ])

    with patch("etf_store._db") as mock_db, \
         patch("etf_store.get_metadata") as mock_meta:
        mock_db.return_value.collection.return_value = fake_collection
        mock_meta.return_value = fake_doc.to_dict()
        n = etf_store.append_daily("TEST", new_df, source="finnhub_delta")

    # Exactly one new row: the genuinely new date. The duplicate is dropped.
    assert n == 1, f"expected 1 appended row, got {n}"


def test_append_daily_returns_zero_when_no_genuinely_new_rows():
    """If every incoming row's date is already stored, append count is 0."""
    fake_doc = MagicMock()
    fake_doc.exists = True
    fake_doc.to_dict.return_value = {
        "symbol": "TEST",
        "last_date": "2026-05-14",
        "total_days": 2,
        "storage_mode": "embedded",
        "prices": [
            {"date": "2026-05-13", "adjusted_close": 100.0, "volume": 1000},
            {"date": "2026-05-14", "adjusted_close": 102.0, "volume": 1500},
        ],
    }
    fake_ref = MagicMock()
    fake_ref.get.return_value = fake_doc
    fake_collection = MagicMock()
    fake_collection.document.return_value = fake_ref

    new_df = _df([
        ("2026-05-13", 100.0, 1000),
        ("2026-05-14", 102.0, 1500),
    ])

    with patch("etf_store._db") as mock_db, \
         patch("etf_store.get_metadata") as mock_meta:
        mock_db.return_value.collection.return_value = fake_collection
        mock_meta.return_value = fake_doc.to_dict()
        n = etf_store.append_daily("TEST", new_df, source="finnhub_delta")

    assert n == 0
