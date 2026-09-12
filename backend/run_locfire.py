#!/usr/bin/env python3
"""Implementation of /locfire command — run local Firebase pipeline."""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from local_config import validate_config


async def run_full_pipeline(target_date=None, dry_run=False):
    """Lazy import of firebase_sync to handle missing dependencies."""
    try:
        from firebase_sync import run_full_pipeline as _run
        return await _run(target_date, dry_run=dry_run)
    except ModuleNotFoundError as e:
        print()
        print("⚠️  Missing dependency: google-cloud-firestore")
        print()
        print("Install with:")
        print("  pip install google-cloud-firestore python-dotenv httpx")
        print()
        print("Then try again or run on Cloud Run (auth automatic).")
        print()
        sys.exit(1)


async def main():
    """Main entry point for /locfire command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run NuWrrrld daily pipeline and sync to Firebase"
    )
    parser.add_argument(
        "date",
        nargs="?",
        type=str,
        help="Target date (YYYY-MM-DD). Default: today",
        default=None,
    )
    parser.add_argument(
        "--docs",
        action="store_true",
        help="Show documentation links after running",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Generate signals but don't sync to Firebase",
    )

    args = parser.parse_args()

    # Parse date if provided
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ Invalid date format: {args.date}")
            print("   Use YYYY-MM-DD format (e.g., 2026-06-25)")
            sys.exit(1)

    # Validate config before running
    valid, missing = validate_config()
    if not valid:
        print()
        print("❌ Configuration Error")
        print(f"   Missing keys: {', '.join(missing)}")
        print()
        print("   Add these to your .env files:")
        print("   - homebase/.env: MISTRAL_KEY, FINNHUB_API_KEY2")
        print("   - gcp3/backend/.env: OPENROUTER_API_KEY")
        print()
        sys.exit(1)

    # Run the pipeline
    if args.no_sync:
        print()
        print("⚠️  Running in dry-run mode (no Firebase sync)")
        print()

    result = await run_full_pipeline(target_date, dry_run=args.no_sync)

    # Show success/failure
    if result.get("status") == "complete":
        exit_code = 0
    else:
        exit_code = 1

    # Show documentation links if requested
    if args.docs:
        print()
        print("📚 Documentation:")
        print("   → Pipeline architecture: /Users/adamaslan/code/homebase/docs/nuwrrrld-pipeline.html")
        print("   → Signal categories: /Users/adamaslan/code/homebase/docs/nuwrrrld-signal-categories.html")
        print("   → Local setup guide: /Users/adamaslan/code/gcp3/backend/README_LOCAL_PIPELINE.md")
        print()

    # Show Firebase console link
    if exit_code == 0:
        target_date_str = (target_date or datetime.today().date()).strftime("%Y-%m-%d")
        print("🔗 View in Firebase Console:")
        print("   → https://console.firebase.google.com/u/0/project/nuwrrrld-prod/firestore/data/gcp3_cache")
        print()
        print(f"   Look for documents with suffix: :{target_date_str}")
        print()

    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
