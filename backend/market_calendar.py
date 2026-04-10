"""Market calendar utilities for trading day awareness and market hours detection."""

from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

_ET = ZoneInfo("America/New_York")
_NYSE_CALENDAR = mcal.get_calendar("NYSE")
_NYSE_HOLIDAYS = set(h.date() for h in _NYSE_CALENDAR.holidays())


def is_trading_day(d: date) -> bool:
    """Return True if d is a NYSE trading day (weekday, not holiday).

    Uses pandas_market_calendars for accurate, always-current holiday data.
    """
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
