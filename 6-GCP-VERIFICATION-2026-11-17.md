# GCP verification update for PR 84

Documentation update. Checked November17,2026,13:35-13:46 America/New_York.

PR: https://github.com/adamaslan/gcp3/pull/84

Reviewed head: `2d1b32f6c8f7cea8f8a131e90d461754d0d4ba5c`. Recheck head before applying instructions.

## Actual checks and results

Exact backend/ai_summary.py and llm/legacy_client.py read. An isolated harness executes the real summary functions with all gather/model/cache boundaries mocked: two exhaustion requests cause one5-source gather and one model attempt; only generic failure text is cached. A second boundary check confirms unrelated exceptions propagate without failure-cache writes and successful recovery is cached with one mocked model attempt. This is source isolation, not the historical four-test suite rerun.

## Findings and remaining uncertainty

Negative caching limits repeated failure cost; it does not fix credentials/model availability. The Cloud Run free-model-refresh Job failed metadata validation401 onNov16, but that is a different job credential/date and cannot settle this backend key now.

## Next instructions

Retain600sec TTL and dedicated exception-only cache semantics. Run original expiry/recovery/unrelated-exception tests at exact rebased head, using mocked data/cache. Reconcile shared legacy_client changes with81/87. Prove successful daily cache and failure cooldown are separate. Do not issue generation requests to test cooldown without route/cost authority.

## Shared acceptance boundary

Current serving backend: `gcp3-backend-00064-2lm`,100% traffic, image digest `sha256:89f8a3b20607fcc3d1e1a40ef28c7d06c1669b1cf303f297cde20bb68f55c172`. Source/build binding absent in console. See [revision](https://console.cloud.google.com/run/detail/us-central1/gcp3-backend/revisions?authuser=1&project=ttb-lang1).

Google Scheduler shows seven paused replacement jobs and one enabled weekly model-refresh dispatcher. GHA latest inspected Slot1 run enables all seven replacement job names and performs purge; paused Google jobs alone are not an outage. [Actual job log](https://github.com/adamaslan/gcp3/actions/runs/44109664868/job/134131490036). HTTP success, dispatch success, fixture tests and source merge are separate from fresh consumer output.

No merge, deployment, workflow dispatch, new credentials, provider/model call, spending, database write or cloud/IAM/API/billing change performed or authorized by this note. Actual Markdown file added to this existing PR for review; implementation follows review and separate effect authority. Local c11 Codex request remains separately tracked and has no actual startup receipt yet.
