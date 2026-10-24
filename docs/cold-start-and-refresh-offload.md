# Cold starts and refresh offload: use GitHub Actions and Modal, not an always-on instance

Written 2026-10-23 from the NWF slowness audit. The decision: do **not** pay for
`--min-instances=1` on `gcp3-backend`. Fix cold starts in code, and move long scheduled work
off the serving service onto the two runners this repo already uses (GitHub Actions and Modal).

## What was measured

Last 24 hours of `gcp3-backend` logs: 3,242 requests and 15 new instances. On the two
instances sampled, **15.7 s and 26 s passed between "Starting new instance" and uvicorn's
"Started server process"**, a log line uvicorn only writes after it has imported
`backend/main.py`. The same import takes about 1.0 s on a laptop, so the 1-vCPU container is
the bottleneck. The first request on a new instance (even `/health`) paid that wait.

Long scheduled jobs also ran on the serving service: `/refresh/fetch` took 232 s and
`/refresh/bake` took 97 s on one instance, which pushes user traffic onto new, cold instances.

## Step 1 (done in this PR): lazy imports

`etf_store` (loaded through `industry`) imported pandas at module load, and `data_client`,
`swing_predictions` and `archiver` imported yfinance, `ta` and pandas. They now import inside the
functions that use them. `import main` no longer loads pandas, yfinance or `ta`, and takes about
0.63 s locally instead of 1.0 s.

The local gain is modest. The cloud effect is not measured yet: check it after deploy with the
log query below. Pandas is still paid on the first request that needs it, so endpoints that read
only from the cache start faster, and data-heavy endpoints save less.

## Step 2 (not done): move long jobs to GitHub Actions and Modal

`feed_tracker.py` is the working pattern. It runs the same code in a GitHub Actions runner
(`.github/workflows/tracker-feed.yml`) and in Modal (`deploy/modal/tracker_feed.py`), writing
straight to Firestore, so it never touches the serving service and keeps working when Cloud Run
is down.

Proposed, in this order, one PR each:

| Job | Today | Proposal |
|---|---|---|
| `/refresh/fetch` (232 s) and `/refresh/bake` (97 s) | Cloud Scheduler calls the serving service | A script that runs the same stages directly, scheduled in GitHub Actions with a Modal cron as the second runner, at staggered times as `tracker-feed.yml` does |
| `/refresh/midday-yf`, `/refresh/intraday` (26–36 s) | Same | Same pattern, after the first one proves out |
| `/admin/purge-cache` (49 s) | Called by hand or by a scheduler | GitHub Actions `workflow_dispatch` plus a weekly cron |

Keep the HTTP endpoints so manual runs still work. Cloud Scheduler can stay as a third trigger
until the new runners have a week of green runs.

**Not recommended: a keep-warm ping.** A GitHub Actions cron runs at best every 5 minutes and is
often delayed, and a warm instance can still be recycled. A Modal cron is steadier, but a ping
still doesn't help the second concurrent request, which starts a new instance anyway. If a ping is
ever tried, use Modal and measure the cold-start count before and after.

## Verify

Cold starts in the last 24 hours (run before and after the deploy). Today it prints 15.

```bash
export GCP3_PROJECT=$(for p in $(gcloud projects list --format='value(projectId)'); do gcloud run services describe gcp3-backend --project "$p" --region us-central1 --format='value(metadata.name)' >/dev/null 2>&1 && echo "$p" && break; done)
gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=gcp3-backend AND textPayload:"Application startup complete"' --project "$GCP3_PROJECT" --freshness=1d --limit 1000 --format='value(timestamp)' | wc -l
```

Time from new instance to listening (the number this PR targets). Compare the gap between each
"Starting new instance" line and the "Started server process" line that follows it on the same
`instanceId`.

```bash
gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=gcp3-backend AND (textPayload:"Starting new instance" OR textPayload:"Started server process")' --project "$GCP3_PROJECT" --freshness=1d --limit 60 --order=asc --format='value(timestamp,labels.instanceId,textPayload)' | cut -c1-120
```

Expect: gaps of roughly 15–26 s before the deploy. After it, a smaller gap. Anything under a few
seconds would mean the import was the whole cost.

Requests slower than 5 s, with the instance that served them:

```bash
gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=gcp3-backend AND httpRequest.latency>"5s"' --project "$GCP3_PROJECT" --freshness=1d --limit 200 --format='value(timestamp,httpRequest.requestUrl,httpRequest.latency,labels.instanceId)' | sed -E 's#https://[^/]+##' | sort
```

Run the existing Modal feed once, as the check for Step 2's runner:

```bash
modal run deploy/modal/tracker_feed.py --check-only
```
