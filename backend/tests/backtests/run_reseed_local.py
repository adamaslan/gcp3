"""Run seed_etf_history locally — yfinance rate-limits Cloud Run IPs so the
deployed force-reseed wiped 50 ETFs and replaced them with 0 rows.
This script reseeds from a residential IP (developer laptop), writing the
fresh history directly to Firestore.

Usage:
    cd backend && GCP_PROJECT_ID=ttb-lang1 python -m tests.backtests.run_reseed_local
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def main() -> None:
    # Read the audit report to know which symbols need reseeding
    report_path = Path(__file__).parent / "reports" / "etf_history_audit.json"
    with open(report_path) as f:
        audit = json.load(f)

    symbols = audit["drifting_symbols"]
    print(f"Local reseed for {len(symbols)} offenders…")

    # The deployed force=true call already wiped these docs, so this is now
    # the seed (full history) path, not a delta append.
    from industry import seed_etf_history
    results = await seed_etf_history(force=False, symbols=symbols)

    success = [s for s, n in results.items() if n > 0]
    failed = [s for s, n in results.items() if n == 0]
    total_rows = sum(results.values())

    print(f"  succeeded: {len(success)}/{len(results)}  ({total_rows} total rows)")
    if failed:
        print(f"  FAILED (0 rows): {failed}")

    out = Path(__file__).parent / "reports" / "etf_history_reseed.json"
    out.write_text(json.dumps({
        "symbols_attempted": symbols,
        "results": results,
        "succeeded": success,
        "failed": failed,
        "total_rows": total_rows,
    }, indent=2))
    print(f"  report → {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")


if __name__ == "__main__":
    asyncio.run(main())
