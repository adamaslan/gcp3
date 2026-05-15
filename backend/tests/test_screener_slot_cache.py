"""Test screener slot-bucketed cache keys (PR follow-up to backtest 2026-05-15).

Locks the behavior that fixed `/screener` quotes drifting >1.5% from Finnhub:
the cache must roll every 15 minutes instead of every 26 hours.
"""
import time
from unittest.mock import patch

import screener


def test_slot_key_is_15min_bucketed():
    """Within a 15-min window the slot key is identical; across windows it differs."""
    # Anchor on a known slot boundary: pick a multiple of 900.
    base = 1_700_000_000 // 900 * 900  # = 1_699_999_500 (last slot boundary at/below 1.7B)
    with patch("screener.time.time", return_value=float(base)):
        k1 = screener._slot_key()
    with patch("screener.time.time", return_value=float(base + 600)):  # +600s = same slot
        k2 = screener._slot_key()
    with patch("screener.time.time", return_value=float(base + 901)):  # +901s = next slot
        k3 = screener._slot_key()
    assert k1 == k2, "same 15-min window must produce same key"
    assert k1 != k3, "next 15-min window must produce different key"
    assert k1.startswith("screener:slot:")


def test_slot_seconds_is_900():
    """Guard against accidentally lengthening the slot back to a daily cache."""
    assert screener._SCREENER_SLOT_SECONDS == 900


def test_daily_key_format():
    assert screener._daily_key().startswith("screener:")
    assert ":slot:" not in screener._daily_key()


def test_slot_and_daily_keys_differ():
    """The two writes must produce distinct Firestore docs."""
    assert screener._slot_key() != screener._daily_key()
