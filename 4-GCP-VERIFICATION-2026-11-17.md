# GCP verification update for PR 87

Documentation update. Checked November17,2026,13:35-13:46 America/New_York.

PR: https://github.com/adamaslan/gcp3/pull/87

Reviewed head: `8e10c6b71e23c6642991b7f477d1a7ce50d2b707`. Recheck head before applying instructions.

## Actual checks and results

Exact backend/llm/legacy_client.py read and syntax checked. OpenRouter chain has a20sec deadline, then _call_mistral remains reachable using mistral-small-latest. Additional offline async test cancels a slow OpenRouter double at the chain deadline, then calls a Mistral double and exceeds that deadline; external cancellation propagates without fallback. Static free-model membership is a dated claim, not catalog proof now.

## Findings and remaining uncertainty

The20sec cap ends the OpenRouter portion, not the entire request including fallback. Mistral fallback is not demonstrated free-only. Neither credentials nor end-to-end generation were probed. PR84 historical401 and87 historical200 apply to different checks/dates.

## Next instructions

Under free-only policy, fail closed before any unpriced fallback unless explicit cost authority exists. Add mocked timeout/cancellation tests proving total deadline behavior and that blocked fallback makes zero provider calls. Reconcile81/84 source overlap and keep cooldown exception compatible. A proposed curl of ai_summary can generate paid or provider work; do not run it as a read-only smoke test.

## Shared acceptance boundary

Current serving backend: `gcp3-backend-00064-2lm`,100% traffic, image digest `sha256:89f8a3b20607fcc3d1e1a40ef28c7d06c1669b1cf303f297cde20bb68f55c172`. Source/build binding absent in console. See [revision](https://console.cloud.google.com/run/detail/us-central1/gcp3-backend/revisions?authuser=1&project=ttb-lang1).

Google Scheduler shows seven paused replacement jobs and one enabled weekly model-refresh dispatcher. GHA latest inspected Slot1 run enables all seven replacement job names and performs purge; paused Google jobs alone are not an outage. [Actual job log](https://github.com/adamaslan/gcp3/actions/runs/44109664868/job/134131490036). HTTP success, dispatch success, fixture tests and source merge are separate from fresh consumer output.

No merge, deployment, workflow dispatch, new credentials, provider/model call, spending, database write or cloud/IAM/API/billing change performed or authorized by this note. Actual Markdown file added to this existing PR for review; implementation follows review and separate effect authority. Local c11 Codex request remains separately tracked and has no actual startup receipt yet.
