# GCP verification update for PR 85

Documentation update. Checked November17,2026,13:35-13:46 America/New_York.

PR: https://github.com/adamaslan/gcp3/pull/85

Reviewed head: `386ae42781028cb204a50e1150c4e1fd17841a4d`. Recheck head before applying instructions.

## Actual checks and results

Exact backend/data_client.py read and syntax checked. AST import-boundary test passes for this file: yfinance import moves inside _yf(); current branch still has Finnhub-first logic rather than83 Alpaca-first implementation. Cloud revision currently shows startup CPU boost and512MiB/1CPU, but no new cold-start comparison was run.

## Findings and remaining uncertainty

Historical local import speedup is not measured Cloud Run latency. It shifts first-use cost. PR83 overlap must not be resolved by discarding its provider/rate-limit changes.

## Next instructions

Rebase after83 using one writer; preserve Alpaca-first/cache behavior and datacenter exclusions while retaining lazy imports. Test first-use accessor and representative indicator path with the pinned ta version. After separately authorized deploy, compare exact same cold-start interval definitions and cache-only/data-heavy endpoints with revision/digest, sample count and p50/p95. No min-instance/spend change as part of this verification.

## Shared acceptance boundary

Current serving backend: `gcp3-backend-00064-2lm`,100% traffic, image digest `sha256:89f8a3b20607fcc3d1e1a40ef28c7d06c1669b1cf303f297cde20bb68f55c172`. Source/build binding absent in console. See [revision](https://console.cloud.google.com/run/detail/us-central1/gcp3-backend/revisions?authuser=1&project=ttb-lang1).

Google Scheduler shows seven paused replacement jobs and one enabled weekly model-refresh dispatcher. GHA latest inspected Slot1 run enables all seven replacement job names and performs purge; paused Google jobs alone are not an outage. [Actual job log](https://github.com/adamaslan/gcp3/actions/runs/44109664868/job/134131490036). HTTP success, dispatch success, fixture tests and source merge are separate from fresh consumer output.

No merge, deployment, workflow dispatch, new credentials, provider/model call, spending, database write or cloud/IAM/API/billing change performed or authorized by this note. Actual Markdown file added to this existing PR for review; implementation follows review and separate effect authority. Local c11 Codex request remains separately tracked and has no actual startup receipt yet.
