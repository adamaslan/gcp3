"""Run the etf_history audit locally — yfinance often rate-limits Cloud Run
IPs, so the deployed /admin/audit-etf-history endpoint returns 54/54 missing.
Running from a developer laptop hits yfinance from a residential IP and
actually gets a usable answer.

Usage:
    cd backend && python -m tests.backtests.run_audit_local
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def main() -> None:
    from industry import audit_etf_history
    result = await audit_etf_history(drift_threshold_pct=1.0)

    print(f"checked: {result['checked']}")
    print(f"missing yfinance: {len(result['missing_yfinance'])}")
    print(f"drifting: {len(result['drifting'])}")
    print()
    if result["drifting"]:
        print("Offenders (drift > 1%):")
        for d in result["drifting"][:30]:
            print(
                f"  {d['symbol']:6s}: stored={d['stored_close']:9.2f} "
                f"yf={d['yfinance_close']:9.2f} drift={d['drift_pct']:6.2f}% "
                f"  ({d['stored_date']} -> {d['yfinance_date']})"
            )

    out = Path(__file__).parent / "reports" / "etf_history_audit.json"
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nFull report → {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")

    if result["drifting"]:
        offenders = ",".join(result["drifting_symbols"])
        print()
        print("To remediate, run:")
        print(f'  SECRET=$(gcloud secrets versions access latest --secret=SCHEDULER_SECRET --project=ttb-lang1)')
        print(f'  curl -X POST "https://gcp3-backend-cif7ppahzq-uc.a.run.app/admin/seed-etf-history?force=true&symbols={offenders}" \\')
        print(f'       -H "X-Scheduler-Token: $SECRET"')


if __name__ == "__main__":
    asyncio.run(main())
