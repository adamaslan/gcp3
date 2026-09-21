"""Feed the industry tracker without going through the Cloud Run backend.

Runs the same three stages the Cloud Scheduler path runs, in-process:

    seed_etf_history  ->  compute_returns  ->  freshness check

and writes straight to Firestore. That independence is the point: GitHub
Actions and Modal both run this file, so neither depends on the Cloud Run
service being up. On 2026-09-08 billing took Cloud Run down for two days while
Firestore stayed writable.

The run exits non-zero when fewer than ``MIN_FRESH_RATIO`` of the tracked ETFs
reached the expected trading day, so a green run means the data is current and
not merely that the job executed.

Usage (needs GCP_PROJECT_ID plus Application Default Credentials):
    python feed_tracker.py
    python feed_tracker.py --check-only    # freshness report, writes nothing
"""
import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone

from market_calendar import is_trading_day

logger = logging.getLogger("feed_tracker")

# Share of tracked ETFs that must have reached the expected trading day.
# 54 symbols, so 0.9 tolerates 5 stragglers (a delisting, a vendor gap)
# while still failing loudly on a wholesale stall like the 09-04 one.
MIN_FRESH_RATIO = 0.9

# Daily bars are final well after the 16:00 ET close. 21:30 UTC is 17:30 ET
# in winter, the later of the two seasons, so a bar dated today is complete.
SESSION_SETTLED_HOUR_UTC = 21
SESSION_SETTLED_MINUTE_UTC = 30


def expected_last_date(now: datetime) -> date:
    """Return the newest trading day whose daily bar should be settled at ``now``."""
    day = now.date()
    settled = (now.hour, now.minute) >= (SESSION_SETTLED_HOUR_UTC, SESSION_SETTLED_MINUTE_UTC)
    if not settled:
        day -= timedelta(days=1)
    while not is_trading_day(day):
        day -= timedelta(days=1)
    return day


def tracked_etfs() -> list[str]:
    """Return the ETF symbols the tracker maps industries to (orphaned docs excluded)."""
    from industry import _FLAT

    return sorted({etf.upper() for _, etf in _FLAT.values()})


def measure_freshness(expected: date) -> dict:
    """Read ``etf_history/{SYMBOL}.last_date`` for every tracked ETF."""
    from firestore import db as get_db

    firestore = get_db()
    symbols = tracked_etfs()
    refs = [firestore.collection("etf_history").document(s) for s in symbols]
    last_dates: dict[str, str | None] = {
        snap.id: (snap.to_dict() or {}).get("last_date") if snap.exists else None
        for snap in firestore.get_all(refs)
    }
    fresh = [s for s, d in last_dates.items() if d and d >= expected.isoformat()]
    stale = sorted(s for s in symbols if s not in fresh)
    return {
        "expected": expected.isoformat(),
        "tracked": len(symbols),
        "fresh": len(fresh),
        "stale": stale,
    }


def freshness_is_ok(report: dict) -> bool:
    return report["tracked"] > 0 and report["fresh"] / report["tracked"] >= MIN_FRESH_RATIO


async def run(check_only: bool) -> int:
    """Seed, recompute, then verify. Returns the process exit code."""
    from industry import compute_returns, seed_etf_history

    if not check_only:
        seeded = await seed_etf_history()
        logger.info("seed: %d ETFs touched, %d rows", len(seeded), sum(seeded.values()))
        computed = await compute_returns()
        logger.info("compute_returns: %s", computed)

    report = measure_freshness(expected_last_date(datetime.now(timezone.utc)))
    logger.info(
        "freshness: %d/%d tracked ETFs at >= %s; stale=%s",
        report["fresh"], report["tracked"], report["expected"], report["stale"],
    )
    if not freshness_is_ok(report):
        logger.error(
            "tracker is stale: %d/%d fresh, need >= %.0f%%",
            report["fresh"], report["tracked"], MIN_FRESH_RATIO * 100,
        )
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check-only", action="store_true", help="report freshness, write nothing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(asyncio.run(run(check_only=args.check_only)))


if __name__ == "__main__":
    main()
