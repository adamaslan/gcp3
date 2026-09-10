# Manual TODO — items no code change can resolve

This file holds only human-blocked work: a billing decision, a dashboard
toggle, a DNS record, a secret that must be set by a person. Append new
entries at the end; never rewrite or re-sort existing ones. Name the
variable, never the value.

---

### ~~Re-enable billing on the `ttb-lang1` GCP project~~ — RESOLVED 2026-09-10
- **From**: 2026-09-10 industry-tracker verification
- **Blocked on**: a billing decision on GCP project `ttb-lang1` — whether
  this was a budget cap, an expired trial, a removed payment method, or a
  billing-account unlink is not visible from the CLI (`gcloud scheduler
  jobs list` returns `BILLING_DISABLED`; `gcloud beta billing` needs a
  component install).
- **Why it can't be code**: Cloud Run refuses to serve while billing is
  disabled. The revision is healthy — `gcp3-backend-00061-qvm` reports
  `Ready=True` — and still returns 503 to every request, including
  `/health`. No deploy, config, or code change affects this.
- **Unblocks**: `/industry-tracker`, `/industry-returns`, `/signals` and
  every other backend route; the Vercel frontend, which currently renders
  an error state with zero industry rows; and the 13:45 UTC Cloud
  Scheduler job that refreshes `industry_cache`.
- **Detail**: last successful request 2026-09-08T18:55:45Z, first
  `billing is disabled` error 2026-09-08T23:16:34Z.
- **Workaround in place**: Firestore is on the free tier and unaffected, so
  the local pipeline (`backend/run_locfire.py`, `industry.compute_returns`)
  keeps tracker data current without Cloud Run. Data is fresh through
  2026-09-10 by that route.
- **Added**: 2026-09-10
- **RESOLVED 2026-09-10**: billing was re-enabled later the same day. Confirmed by
  `gcloud scheduler jobs list` returning all 8 jobs ENABLED (it had returned
  `BILLING_DISABLED`), and by the `billing is disabled` log entries stopping.
  Cloud Run then returned 429 "Rate exceeded" / "no available instance" for a
  period while cold-starting back up — expected recovery behavior after a
  project reactivation, not a second fault.

### Cloud Run dies under a cold-cache request storm after the outage
- **From**: 2026-09-10, after billing was restored
- **Blocked on**: a resource/concurrency decision — raise memory above 512Mi,
  raise `maxScale` above 5, and/or warm the caches in a controlled order before
  exposing the service to general traffic.
- **Why it is not a code bug**: the deployed revision is **fine**. In the one
  window where an instance lived (21:38:28-21:38:53Z) it served
  `/industry-returns`, `/industry-intel` and `/signals` all 200 — `/signals`
  built 54 symbols and 255 signals off the refreshed data. It then died, and
  every request since is `429 Rate exceeded` / `no available instance`.
- **What is actually happening**: two days of outage left **every cache key
  cold**. On the first instance `morning_brief`, `sector_rotation`,
  `macro_pulse`, `screener` and `news_sentiment` all cache-missed *at once* and
  fanned out to Finnhub concurrently. The service is `memory=512Mi`, `cpu=1`,
  `maxScale=5`, `containerConcurrency=80`, `timeout=300`. That burst kills the
  instance; the next request finds none; callers retry; the retries deny it a
  quiet start. A thundering herd on cold cache — a self-inflicted recovery
  storm, not an external limit.
- **Ruled out — NOT a project-wide quota throttle**: two sibling Cloud Run
  services in the same project and region (`technical-analysis-api`,
  `technical-analysis-mcp`) return 200 throughout. An earlier revision of this
  entry blamed post-reactivation quota restriction; **that was wrong.**
- **Ruled out — Finnhub is not the problem**: `/quote` returns 200 OK all
  through those logs. Only `/stock/candle` is paid-tier.
- **Unblocks**: the cloud backend serving again, and the 8 scheduler jobs that
  are ENABLED and firing at a service that 429s.
- **Not urgent for data**: tracker data is current through 2026-09-10 via the
  local path, which needs neither Cloud Run nor billing.
- **Added**: 2026-09-10

### Create the DNS record for `sectors.nuwrrrld.com`
- **From**: 2026-09-10 industry-tracker verification
- **Blocked on**: adding the record in Cloudflare (zone for `nuwrrrld.com`)
  pointing at the Vercel project `gcp3-frontend`.
- **Why it can't be code**: the domain is already attached on the Vercel
  side; what is missing is the DNS record itself, which lives in the
  Cloudflare zone and needs an account-level change.
- **Unblocks**: reaching the industry tracker UI at its intended hostname.
  Today it resolves to nothing (`dig +short` returns empty) and is only
  reachable at `gcp3-frontend.vercel.app`.
- **Added**: 2026-09-10

### Decide whether `MISTRAL_KEY` should back a real Mistral provider
- **From**: 2026-09-10, porting the router fix after PR #77
- **Blocked on**: a decision, not a key. `llm/providers/mistral.py` is still
  a placeholder that raises unconditionally, so `mistral` — the second
  entry in `DEFAULT_LLM_PROVIDER_ORDER` — cannot actually serve as the
  fallback it is listed as. `MISTRAL_KEY` is already bound in cloudbuild.
- **Why it can't be code**: implementing it is code, but whether Mistral
  should be the fallback at all (vs. a second OpenRouter model, vs. no
  fallback) is a cost/quality call.
- **Unblocks**: a real two-provider chain. Today, if OpenRouter fails the
  gateway degrades immediately.
- **Added**: 2026-09-10
