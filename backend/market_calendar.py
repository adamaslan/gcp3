"""Market calendar utilities for trading day awareness and market hours detection."""

from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# NYSE holidays 2026–2027 (hardcoded — extend annually as needed)
_NYSE_HOLIDAYS_2026 = {
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents Day
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 7, 3),    # Independence Day (observed)
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
}

_NYSE_HOLIDAYS_2027 = {
    date(2027, 1, 1),    # New Year's Day
    date(2027, 1, 18),   # MLK Day
    date(2027, 2, 15),   # Presidents Day
    date(2027, 3, 26),   # Good Friday
    date(2027, 5, 31),   # Memorial Day
    date(2027, 7, 5),    # Independence Day (observed)
    date(2027, 9, 6),    # Labor Day
    date(2027, 11, 25),  # Thanksgiving
    date(2027, 12, 25),  # Christmas
}

_NYSE_HOLIDAYS = _NYSE_HOLIDAYS_2026 | _NYSE_HOLIDAYS_2027


def is_trading_day(d: date) -> bool:
    """Return True if d is a NYSE trading day (weekday, not holiday)."""
    return d.weekday() < 5 and d not in _NYSE_HOLIDAYS


def trading_date() -> date:
    """Return the most recent completed trading day in ET.

    This is the "effective trading date" for cache keys and data freshness.
    The market close is 4:00 PM ET. After 4:00 PM ET on a trading day,
    the trading date is that day. Before 4:00 PM ET, the trading date is
    the previous trading day.
    """
    now_et = datetime.now(_ET)
    d = now_et.date()

    # If before market close (4:00 PM ET), use yesterday's trading date
    if now_et.time() < time(16, 0):
        d = d - timedelta(days=1)

    # Walk backward to find most recent trading day
    while not is_trading_day(d):
        d = d - timedelta(days=1)

    return d


def is_market_open() -> bool:
    """Return True if US equity market is currently in regular session (ET).

    Regular session is 9:30 AM – 4:00 PM ET on trading days.
    """
    now_et = datetime.now(_ET)
    if not is_trading_day(now_et.date()):
        return False
    market_open = time(9, 30)
    market_close = time(16, 0)
    return market_open <= now_et.time() < market_close
