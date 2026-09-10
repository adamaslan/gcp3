"""Firebase synchronization for local pipeline runs.

Pulls results from each pipeline stage and writes them to Firestore collections
and documents with proper TTL handling. Designed for local development and testing.
"""
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

# Ensure local_config is loaded
from local_config import get_config, validate_config

logger = logging.getLogger(__name__)

# Initialize Firestore with GCP project from config
_db = None


def _get_db() -> firestore.Client:
    """Get or create Firestore client with configured project ID."""
    global _db
    if _db is None:
        config = get_config()
        project_id = config.get("gcp_project_id")
        if not project_id:
            raise RuntimeError("GCP_PROJECT_ID not configured — cannot initialize Firestore")
        _db = firestore.Client(project=project_id)
    return _db


async def sync_cache_entry(
    key: str,
    value: dict | list,
    collection: str = "gcp3_cache",
    ttl_hours: int = 24,
) -> bool:
    """Write a cache entry to Firestore with TTL.

    Args:
        key: Document key (e.g., "technical_signals:all:2026-06-25")
        value: Data to write
        collection: Collection name (default: "gcp3_cache")
        ttl_hours: Hours until expiration (default: 24)

    Returns:
        True if successful, False otherwise
    """
    try:
        db = _get_db()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ttl_hours)

        doc_data = {
            "key": key,
            "value": value,
            "updated_at": now,
            "expires_at": expires_at,
        }

        db.collection(collection).document(key).set(doc_data)
        logger.info(f"✅ Synced {collection}/{key} ({len(str(value))} bytes, TTL {ttl_hours}h)")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to sync {key}: {e}")
        return False


async def sync_technical_signals(target_date: date = None) -> dict | None:
    """Fetch technical signals and sync to Firebase."""
    try:
        from technical_signals import get_technical_signals

        target_date = target_date or date.today()
        logger.info(f"📊 Generating technical signals for {target_date}...")

        signals = await get_technical_signals()
        key = f"technical_signals:all:{target_date}"

        success = await sync_cache_entry(key, signals, "gcp3_cache", ttl_hours=24)
        if success:
            return {
                "stage": "technical_signals",
                "date": str(target_date),
                "signal_count": len(signals) if isinstance(signals, list) else 1,
                "status": "success",
            }
    except Exception as e:
        logger.error(f"❌ Technical signals failed: {e}")
        import traceback

        traceback.print_exc()
    return None


async def sync_ai_summary(target_date: date = None) -> dict | None:
    """Fetch AI summary and sync to Firebase."""
    try:
        from ai_summary import get_ai_summary

        target_date = target_date or date.today()
        logger.info(f"🧠 Generating AI summary for {target_date}...")

        summary = await get_ai_summary()
        key = f"ai_summary:{target_date}"

        success = await sync_cache_entry(key, summary, "gcp3_cache", ttl_hours=24)
        if success:
            brief_len = len(summary.get("brief", "")) if isinstance(summary, dict) else 0
            return {
                "stage": "ai_summary",
                "date": str(target_date),
                "brief_length": brief_len,
                "status": "success",
            }
    except Exception as e:
        logger.error(f"❌ AI summary failed: {e}")
        import traceback

        traceback.print_exc()
    return None


async def sync_sector_rotation(target_date: date = None) -> dict | None:
    """Fetch sector rotation and sync to Firebase."""
    try:
        from sector_rotation import get_sector_rotation

        target_date = target_date or date.today()
        logger.info(f"🔄 Sector rotation analysis for {target_date}...")

        rotation = await get_sector_rotation()
        key = f"sector_rotation:{target_date}"

        success = await sync_cache_entry(key, rotation, "gcp3_cache", ttl_hours=24)
        if success:
            leaders = len(rotation.get("leaders", [])) if isinstance(rotation, dict) else 0
            return {
                "stage": "sector_rotation",
                "date": str(target_date),
                "leaders_count": leaders,
                "status": "success",
            }
    except Exception as e:
        logger.error(f"❌ Sector rotation failed: {e}")
        import traceback

        traceback.print_exc()
    return None


async def sync_macro_pulse(target_date: date = None) -> dict | None:
    """Fetch macro pulse and sync to Firebase."""
    try:
        from macro_pulse import get_macro_pulse

        target_date = target_date or date.today()
        logger.info(f"📈 Macro pulse analysis for {target_date}...")

        macro = await get_macro_pulse()
        key = f"macro_pulse:{target_date}"

        success = await sync_cache_entry(key, macro, "gcp3_cache", ttl_hours=24)
        if success:
            return {
                "stage": "macro_pulse",
                "date": str(target_date),
                "status": "success",
            }
    except Exception as e:
        logger.error(f"❌ Macro pulse failed: {e}")
        import traceback

        traceback.print_exc()
    return None


async def sync_morning_brief(target_date: date = None) -> dict | None:
    """Fetch morning brief and sync to Firebase."""
    try:
        from morning import get_morning_brief

        target_date = target_date or date.today()
        logger.info(f"🌅 Morning brief for {target_date}...")

        brief = await get_morning_brief()
        key = f"morning_brief:{target_date}"

        success = await sync_cache_entry(key, brief, "gcp3_cache", ttl_hours=24)
        if success:
            return {
                "stage": "morning_brief",
                "date": str(target_date),
                "status": "success",
            }
    except Exception as e:
        logger.error(f"❌ Morning brief failed: {e}")
        import traceback

        traceback.print_exc()
    return None


async def run_full_pipeline(target_date: date = None) -> dict:
    """Run all pipeline stages and sync to Firebase.

    Args:
        target_date: Date to generate for (default: today)

    Returns:
        Summary dict with results from each stage
    """
    target_date = target_date or date.today()

    print()
    print("=" * 70)
    print(f"🚀 NuWrrrld Pipeline — Local Run for {target_date}")
    print("=" * 70)
    print()

    # Validate config first
    valid, missing = validate_config()
    if not valid:
        print(f"❌ Missing configuration: {', '.join(missing)}")
        print("   Set environment variables or add to .env files")
        return {"status": "error", "error": f"Missing config: {missing}"}

    # Run all stages in parallel
    results = await asyncio.gather(
        sync_technical_signals(target_date),
        sync_ai_summary(target_date),
        sync_sector_rotation(target_date),
        sync_macro_pulse(target_date),
        sync_morning_brief(target_date),
    )

    successful = [r for r in results if r and r.get("status") == "success"]

    print()
    print("=" * 70)
    print(f"✅ Pipeline Complete: {len(successful)}/5 stages succeeded")
    print("=" * 70)
    print()

    for result in successful:
        print(f"  {result.get('stage'):20s} → {result.get('status'):10s}")

    return {
        "status": "complete" if len(successful) == 5 else "partial",
        "date": str(target_date),
        "successful_stages": len(successful),
        "results": {r.get("stage"): r for r in results if r},
    }


if __name__ == "__main__":
    import argparse

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    parser = argparse.ArgumentParser(description="Run NuWrrrld pipeline and sync to Firebase")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD)", default=None)
    args = parser.parse_args()

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ Invalid date format: {args.date}. Use YYYY-MM-DD")
            sys.exit(1)

    result = asyncio.run(run_full_pipeline(target_date))
    sys.exit(0 if result.get("status") == "complete" else 1)
