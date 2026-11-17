# GCP verification update for PR 88

Documentation update. Checked November17,2026,13:35-13:46 America/New_York.

PR: https://github.com/adamaslan/gcp3/pull/88

Reviewed head: `9621d398a2178dc3104e1d2663e6575178e8a3e5`. Recheck head before applying instructions.

## Actual checks and results

Exact market_calendar.py and etf_store.py read at9621d398. Two settle-boundary controls pass at22:29/22:30UTC. A new deterministic test fails at2026-11-17T00:30Z, which isNov16 19:30EST: session_settled falsely returnsfalse after UTC midnight. Executing actual _drop_unsettled_today with an ETNov16 fixture drops the already-finalNov16 row. No Firestore or providers.

## Findings and remaining uncertainty

SOURCE BLOCKER: UTC-clock reset breaks the same ET session after midnightUTC. This is unmerged/offline behavior, not proven production impact. Body31tests/200pass claims are historical and were not rerun here. Serving October14 image is not bound to this commit.

## Next instructions

Add the failing same-ET-session rollover regression before repair. Compute settlement against the relevant ET session date plus its UTC cutoff, not hour-of-day alone. Cover winter/summer UTC midnight, before and after ET midnight, weekend and early-close behavior without treating unknown calendars as certified. Run freshness/storage tests and89 compatibility at the repaired exact head. Preserve WITHHELD as non-actionable and distinguish source guards from provider/data repair. Do not reseed or deploy under this review.

## Shared acceptance boundary

Current serving backend: `gcp3-backend-00064-2lm`,100% traffic, image digest `sha256:89f8a3b20607fcc3d1e1a40ef28c7d06c1669b1cf303f297cde20bb68f55c172`. Source/build binding absent in console. See [revision](https://console.cloud.google.com/run/detail/us-central1/gcp3-backend/revisions?authuser=1&project=ttb-lang1).

Google Scheduler shows seven paused replacement jobs and one enabled weekly model-refresh dispatcher. GHA latest inspected Slot1 run enables all seven replacement job names and performs purge; paused Google jobs alone are not an outage. [Actual job log](https://github.com/adamaslan/gcp3/actions/runs/44109664868/job/134131490036). HTTP success, dispatch success, fixture tests and source merge are separate from fresh consumer output.

No merge, deployment, workflow dispatch, new credentials, provider/model call, spending, database write or cloud/IAM/API/billing change performed or authorized by this note. Actual Markdown file added to this existing PR for review; implementation follows review and separate effect authority. Local c11 Codex request remains separately tracked and has no actual startup receipt yet.
