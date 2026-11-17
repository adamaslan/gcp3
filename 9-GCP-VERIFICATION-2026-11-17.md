# GCP verification update for PR 81

Documentation update. Checked November17,2026,13:35-13:46 America/New_York.

PR: https://github.com/adamaslan/gcp3/pull/81

Reviewed head: `b30fd3f810b180fee3caa5d48c10c47fa12d3c2c`. Recheck head before applying instructions.

## Actual checks and results

Source checked: backend/run_local_backup.sh and backend/cloudbuild.yaml. bash -n and safe --list both pass at the pinned source. Invalid-job test exits2 before secret loading/app startup. Neither --dry-run nor refresh was run. The live revision still references both Gemini and OpenRouter secrets, matching older deployed configuration rather than proving this PR is live.

## Findings and remaining uncertainty

The script labels Firestore current when all selected calls returned200. That is not freshness/coverage/readback proof. Its dry-run still reads Secret Manager and boots the real Firestore-backed app. It bypasses Cloud Run compute, not GCP identity, Firestore or Secret Manager dependencies.

## Next instructions

Replace the success claim with HTTP-only status unless a separate readback verifies eligible/written/failed counts, market session and oldest/newest data_as_of. Label dry-run dependencies honestly and add a strictly offline contract check. Reconcile overlapping legacy_client changes with84/87 in one writer lane. Preserve full secret replacement semantics and require explicit deployment authority; no instructions to deploy merely because merge occurs.

## Shared acceptance boundary

Current serving backend: `gcp3-backend-00064-2lm`,100% traffic, image digest `sha256:89f8a3b20607fcc3d1e1a40ef28c7d06c1669b1cf303f297cde20bb68f55c172`. Source/build binding absent in console. See [revision](https://console.cloud.google.com/run/detail/us-central1/gcp3-backend/revisions?authuser=1&project=ttb-lang1).

Google Scheduler shows seven paused replacement jobs and one enabled weekly model-refresh dispatcher. GHA latest inspected Slot1 run enables all seven replacement job names and performs purge; paused Google jobs alone are not an outage. [Actual job log](https://github.com/adamaslan/gcp3/actions/runs/44109664868/job/134131490036). HTTP success, dispatch success, fixture tests and source merge are separate from fresh consumer output.

No merge, deployment, workflow dispatch, new credentials, provider/model call, spending, database write or cloud/IAM/API/billing change performed or authorized by this note. Actual Markdown file added to this existing PR for review; implementation follows review and separate effect authority. Local c11 Codex request remains separately tracked and has no actual startup receipt yet.
