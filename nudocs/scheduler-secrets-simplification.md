# Scheduler Auth & Secrets Simplification

## What Went Wrong (April 2026)

### The Problem Chain

1. **`SCHEDULER_SECRET` was in Secret Manager** — revision `00023` and earlier read it via `--set-secrets`.
2. **Someone manually redeployed revision `00027`** with `--set-env-vars SCHEDULER_SECRET=<new-token>`, bypassing Secret Manager. The new token was NOT written back to Secret Manager.
3. **`cloudbuild.yaml` never included `SCHEDULER_SECRET`** in its `--set-secrets` line. So every Cloud Build deploy wiped the token entirely from Cloud Run.
4. **Two scheduler jobs** (`gcp3-nightly-cache-purge`, `gcp3-premarket-warmup`) still had the OLD token AND the old backend URL from before the service was redeployed. They had never run successfully.
5. **Result**: every scheduled refresh got 401, Firestore cache went stale, `industry-returns` showed Apr 7 data on Apr 8.

### Secondary Bug

`market_summary.py` used `firestore.Query.DESCENDING` without importing `google.cloud.firestore`. This caused the `firestore_readers` stage in `/refresh/all` to error silently, masking any cache-warming of market summaries.

---

## The Fix Applied

1. Added `from google.cloud import firestore` to `market_summary.py`.
2. Added `SCHEDULER_SECRET=SCHEDULER_SECRET:latest` to `cloudbuild.yaml --set-secrets` so deploys never drop it.
3. Updated Secret Manager `SCHEDULER_SECRET` to the value the scheduler jobs were already sending.
4. Updated `gcp3-nightly-cache-purge` and `gcp3-premarket-warmup` jobs to use the correct backend URL and token.

---

## How to Keep This From Happening Again

### Rule 1: Never set secrets as plain `--set-env-vars`

```bash
# ❌ Wrong — bypasses Secret Manager, creates drift
gcloud run deploy gcp3-backend --set-env-vars=SCHEDULER_SECRET=abc123

# ✅ Right — always use Secret Manager reference
gcloud run deploy gcp3-backend --set-secrets=SCHEDULER_SECRET=SCHEDULER_SECRET:latest
```

### Rule 2: `cloudbuild.yaml` is the source of truth for what Cloud Run gets

Every secret the service needs must be listed in `cloudbuild.yaml`. A `gcloud run deploy` command not in `cloudbuild.yaml` creates drift. Current correct state:

```yaml
- --set-secrets=FINNHUB_API_KEY=FINNHUB_API_KEY:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest,SCHEDULER_SECRET=SCHEDULER_SECRET:latest
```

### Rule 3: When rotating a token, update Secret Manager first

```bash
# 1. Generate new token
NEW_TOKEN=$(openssl rand -hex 32)

# 2. Update Secret Manager
echo -n "$NEW_TOKEN" | gcloud secrets versions add SCHEDULER_SECRET --project ttb-lang1 --data-file=-

# 3. Update ALL scheduler jobs
for JOB in gcp3-ai-summary-refresh gcp3-premarket-warmup gcp3-midday-intraday-refresh gcp3-eod-intraday-refresh gcp3-nightly-cache-purge; do
  gcloud scheduler jobs update http "$JOB" \
    --location us-central1 --project ttb-lang1 \
    --update-headers "X-Scheduler-Token=$NEW_TOKEN"
done

# 4. Redeploy backend (picks up new SM value automatically)
cd backend && gcloud builds submit --config cloudbuild.yaml --project ttb-lang1

# 5. Run /post-deploy-verify to confirm all tokens align
```

### Rule 4: When redeploying, update scheduler job URIs if the backend URL changes

Cloud Run service URLs are stable (e.g. `gcp3-backend-cif7ppahzq-uc.a.run.app`) unless the service is deleted and recreated. But if the URL ever changes:

```bash
NEW_URL="https://gcp3-backend-NEWURL-uc.a.run.app"
for JOB in gcp3-ai-summary-refresh gcp3-premarket-warmup gcp3-midday-intraday-refresh gcp3-eod-intraday-refresh gcp3-nightly-cache-purge; do
  # Get current path suffix (e.g. /refresh/all)
  CURRENT_URI=$(gcloud scheduler jobs describe "$JOB" --location us-central1 --project ttb-lang1 --format="value(httpTarget.uri)")
  PATH_SUFFIX="${CURRENT_URI#*run.app}"
  gcloud scheduler jobs update http "$JOB" \
    --location us-central1 --project ttb-lang1 \
    --uri "${NEW_URL}${PATH_SUFFIX}"
done
```

---

## Simplified Architecture (Recommended)

Instead of maintaining tokens manually, consider switching to Cloud Run's native auth:

### Option A: Use OIDC (Google-managed tokens) — No custom token needed

```bash
# 1. Give scheduler permission to invoke Cloud Run
gcloud run services add-iam-policy-binding gcp3-backend \
  --region us-central1 --project ttb-lang1 \
  --member="serviceAccount:gcp3-scheduler@ttb-lang1.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# 2. Update scheduler jobs to use OIDC
for JOB in ...; do
  gcloud scheduler jobs update http "$JOB" \
    --oidc-service-account-email gcp3-scheduler@ttb-lang1.iam.gserviceaccount.com \
    --oidc-token-audience https://gcp3-backend-cif7ppahzq-uc.a.run.app
done

# 3. Make Cloud Run private (remove allUsers)
gcloud run services remove-iam-policy-binding gcp3-backend \
  --region us-central1 --project ttb-lang1 \
  --member="allUsers" --role="roles/run.invoker"
```

**Tradeoff**: More secure (no token to rotate), but the service can no longer be hit directly from a browser. Public endpoints (like `/industry-returns`, `/health`) would need a separate public service or an API gateway.

#### Why public endpoints become a problem

When Cloud Run requires authentication (`allUsers` removed), every request must carry a valid Google-signed OIDC token. A browser making a plain `fetch()` to `/industry-returns` has no such token — it would get a 403 immediately. This affects:

- The Vercel frontend calling the backend via `BACKEND_URL` (server-side fetches from Next.js SSR)
- Anyone hitting the API directly (e.g. `/health` checks, curl)
- The `/api/*` proxy routes in Next.js that forward browser requests to the backend

The Vercel server-side fetch **could** be fixed — Next.js runs on Google infrastructure in some setups, but not on Vercel. Vercel's servers are not Google-signed, so they can't auto-obtain OIDC tokens for your Cloud Run service.

#### Practical options if you go private

**Option A1: Split the service into public + private**

Deploy two Cloud Run services from the same image:
- `gcp3-backend` — private, receives scheduler jobs only (`/refresh/*`, `/admin/*`)
- `gcp3-backend-public` — public (`allUsers`), serves all read endpoints

Scheduler jobs hit the private service. Vercel/browsers hit the public service. No auth token required on the public side.

Downside: two services to deploy, two Cloud Build pipelines, doubled cold-start costs.

**Option A2: Keep one service, add a Cloud Run Ingress rule**

Cloud Run supports an internal ingress mode where only requests from within the same VPC or from Cloud Scheduler/other GCP services are allowed. Public internet is blocked at the network level before IAM checks.

```bash
# Restrict ingress to internal + load balancer only
gcloud run services update gcp3-backend \
  --ingress=internal-and-cloud-load-balancing \
  --region us-central1 --project PROJECT_ID
```

Then put a Google Cloud Load Balancer with a serverless NEG in front. The load balancer is public; the Cloud Run service is only reachable through it or from internal GCP services. Cloud Scheduler can still reach it because scheduler is a GCP-internal caller.

Downside: Load balancer costs ~$20/month minimum. Adds complexity. Overkill for current scale.

**Option A3: Use a service account on Vercel (via env var)**

Generate a service account key for a dedicated SA with `roles/run.invoker`, store it in Vercel as an env var, and use it to mint OIDC tokens before each backend call. This is the most secure path if you want a private Cloud Run service called from Vercel.

Downside: service account key management is exactly the problem OIDC was meant to avoid. Rotate it quarterly.

#### Recommendation for gcp3 current scale

**Stick with Option B (custom token + rotation script) for now.** The backend is already public (`allUsers`), the token approach works, and the drift issue is now fixed in `cloudbuild.yaml`. Go private (Option A) only if:
- You need to prevent direct API access from the internet
- You add a load balancer for rate limiting or WAF anyway
- You split the service into public-read / private-write

### Option B: Keep custom token, but make rotation a single command

Add a `rotate-scheduler-token.sh` script:

```bash
#!/usr/bin/env bash
# rotate-scheduler-token.sh — rotates SCHEDULER_SECRET in sync everywhere
set -euo pipefail
PROJECT="${1:-ttb-lang1}"
REGION="us-central1"

NEW_TOKEN=$(openssl rand -hex 32)
echo "New token: ${NEW_TOKEN:0:8}..."

echo -n "$NEW_TOKEN" | gcloud secrets versions add SCHEDULER_SECRET --project "$PROJECT" --data-file=-
echo "✅ Secret Manager updated"

for JOB in gcp3-ai-summary-refresh gcp3-premarket-warmup gcp3-midday-intraday-refresh gcp3-eod-intraday-refresh gcp3-nightly-cache-purge; do
  gcloud scheduler jobs update http "$JOB" \
    --location "$REGION" --project "$PROJECT" \
    --update-headers "X-Scheduler-Token=$NEW_TOKEN" 2>/dev/null && echo "✅ $JOB updated" || echo "⚠️  $JOB not found"
done

cd "$(dirname "$0")/backend"
gcloud builds submit --config cloudbuild.yaml --project "$PROJECT"
echo "✅ Backend redeployed with new token"
```

---

## Checklist After Any Deploy

Run `/post-deploy-verify` — it now checks:
- [ ] `SCHEDULER_SECRET` present on Cloud Run
- [ ] Secret Manager token matches scheduler job tokens
- [ ] All scheduler job URIs point to the correct backend URL
- [ ] `/refresh/all` returns 401 without a token (auth gate is live)
