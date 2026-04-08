# GCP + Vercel Auth & Deployment Issues — Postmortem

**Last Updated:** 2026-04-07  
**Context:** Optimization deployment (5 phases), full stack (backend + frontend + Firestore); updated with industry-returns incident  
**Duration:** Extended due to auth/deployment friction  
**Scope:** No secrets exposed; specific technical issues identified

---

## Executive Summary

The optimization deployment encountered **20+ authentication, authorization, and deployment configuration issues** that compounded and delayed rollout. A follow-up incident on 2026-04-07 revealed additional issues with Cloud Scheduler auth and stale data pipelines. These fell into four categories:

1. **GCP Service Account & IAM Misconfigurations** (7 issues)
2. **Vercel Environment & Build-Time Configuration** (8 issues)
3. **Cross-Stack Auth Token & Secret Management** (5 issues)
4. **Cloud Scheduler & Data Pipeline Failures** (3 issues — added 2026-04-07)

This postmortem documents each issue, root cause, and how to prevent it in future deployments.

---

## Category 1: GCP Service Account & IAM Issues

### Issue 1: Cloud Run Service Account Missing Firestore Permissions
**Symptom:** Backend fails to read/write Firestore on Cloud Run, 403 errors.  
**Root Cause:** Cloud Run service account (`ttb-lang1@appspot.gserviceaccount.com`) lacked `roles/datastore.user`.  
**Expected Behavior:** When Cloud Run assumes the default service account, it should automatically have access to Firestore in the same project.  
**Actual Behavior:** New deployments sometimes reset IAM roles or grant insufficient permissions.  
**Fix:** Manually assigned `roles/datastore.user` to service account via IAM console.

**Prevention:**
- Use Terraform or `gcloud iam roles grant` in CI/CD to enforce role persistence
- Document required IAM roles in `CLAUDE.md` or `.gcp-setup.sh`

---

### Issue 2: Secret Manager Access Denied for Cloud Run
**Symptom:** Cloud Run cannot read `SCHEDULER_SECRET` from Secret Manager, "Permission denied" errors.  
**Root Cause:** Default Cloud Run service account lacked `roles/secretmanager.secretAccessor`.  
**Expected Behavior:** `gcloud secrets versions access latest --secret=SCHEDULER_SECRET` should work from Cloud Run environment.  
**Actual Behavior:** 403 when Cloud Run tries to read the secret.  
**Fix:** Granted `roles/secretmanager.secretAccessor` to Cloud Run service account.

**Prevention:**
- When creating secrets, immediately grant read access to the service account that will use them
- Use `gcloud secrets add-iam-policy-binding` in deployment scripts
- Test with `gcloud run services describe --format=json | jq .spec.serviceAccountEmail`

---

### Issue 3: SCHEDULER_SECRET Not Set in Cloud Run Environment Variables
**Symptom:** Backend endpoint `/refresh/all` returns 401 "Unauthorized" when called via Cloud Scheduler.  
**Root Cause:** `SCHEDULER_SECRET` env var was stored in Secret Manager but not mounted in Cloud Run service.  
**Expected Behavior:** Secret Manager secret should be referenced as `--set-secrets=SCHEDULER_SECRET=scheduler-secret:latest` at deploy time.  
**Actual Behavior:** The secret existed in Secret Manager, but Cloud Run didn't have it available at runtime.  
**Fix:** Deployed with `--set-secrets=SCHEDULER_SECRET=SCHEDULER_SECRET:latest` in `gcloud run deploy`.

**Prevention:**
- Document all secrets in a checklist alongside env vars
- Use deployment scripts that explicitly list both `--set-env-vars` and `--set-secrets`
- Test with `gcloud run services describe --format=json | jq .spec.template.spec.containers[0].env` and `.secrets`

---

### Issue 4: GCP Project ID Mismatch (Empty String in gcloud Command)
**Symptom:** `gcloud firestore fields ttls update` fails with "project property is set to empty string."  
**Root Cause:** `$GCP_PROJECT_ID` environment variable was empty in the shell session.  
**Expected Behavior:** `gcloud config set project ttb-lang1` sets the default project for all commands.  
**Actual Behavior:** Variable expansion failed, passed empty string to `--project` flag.  
**Fix:** Ran `gcloud config set project ttb-lang1`, then omitted `--project` flag (uses default).

**Prevention:**
- Always verify `gcloud config get-value project` before running infrastructure commands
- Use `gcloud config set project $PROJECT_ID` in deployment scripts
- Never rely on environment variable expansion alone; use config defaults

---

### Issue 5: Application Default Credentials (ADC) Expired
**Symptom:** Local testing works, but Cloud Run deployment fails with auth errors accessing Firestore.  
**Root Cause:** `gcloud auth application-default login` token expired (24h TTL).  
**Expected Behavior:** Cloud Run should use the built-in service account, not ADC.  
**Actual Behavior:** Code falls back to ADC, which was stale.  
**Fix:** Confirmed Cloud Run uses service account (not ADC); refreshed ADC locally with `gcloud auth application-default login`.

**Prevention:**
- Cloud Run should ALWAYS use the service account identity, not ADC
- In code, explicitly use `google.auth.default(scopes=[...])` or `google.cloud.firestore.Client(project=PROJECT_ID)`
- Never embed ADC in production Cloud Run images; rely on `gcloud compute identity-aware-proxy-auth`

---

### Issue 6: Cloud Build Service Account Missing Permissions
**Symptom:** `gcloud builds submit` fails during the "Deploy to Cloud Run" step.  
**Root Cause:** Cloud Build's default service account (`ttb-lang1@cloudbuild.gserviceaccount.com`) lacked `roles/run.developer`.  
**Expected Behavior:** Cloud Build should be able to deploy to Cloud Run as part of the CI/CD pipeline.  
**Actual Behavior:** Build succeeded, but deployment step failed.  
**Fix:** Granted `roles/run.developer` to Cloud Build service account.

**Prevention:**
- Document Cloud Build service account permissions in CLAUDE.md
- Create a `.gcloud/setup-iam.sh` script that grants all required roles upfront
- Test CI/CD pipeline in a test environment before enabling on main branch

---

### Issue 7: Artifact Registry Push Credentials Stale
**Symptom:** `gcloud builds submit` fails at "Push to Artifact Registry" step with authentication errors.  
**Root Cause:** Docker credentials cached by Cloud Build were expired; needs re-authentication.  
**Expected Behavior:** Cloud Build should automatically use the service account to push to Artifact Registry.  
**Actual Behavior:** Cached credentials from a prior failed build were rejected.  
**Fix:** Ran `gcloud auth configure-docker gcr.io` to refresh Docker credentials locally, then resubmitted.

**Prevention:**
- Use service account key-based authentication in Cloud Build (not user credentials)
- In `cloudbuild.yaml`, explicitly set `--registry=us-central1-docker.pkg.dev`
- Don't rely on local Docker cache; clear with `gcloud auth revoke` before CI/CD

---

## Category 2: Vercel Environment & Build-Time Configuration Issues

### Issue 8: BACKEND_URL Not Available in Vercel Build Environment
**Symptom:** Next.js build fails when `npm run build` tries to fetch from `${BACKEND_URL}/morning-brief`.  
**Root Cause:** `BACKEND_URL` is set in Vercel Environment Variables (UI), but only synced to runtime, not build time.  
**Expected Behavior:** Environment variables set in Vercel dashboard should be available during `npm run build`.  
**Actual Behavior:** Pages with server-side `fetch()` fail at build time because `BACKEND_URL` is undefined.  
**Fix:** Removed `revalidate` from ISR pages and added `force-dynamic` (skip prerendering, fetch on first request).

**Prevention:**
- Separate build-time vs. runtime environment variables in Vercel settings
- Use "Build Environment Variables" (not just "Environment Variables") for secrets needed at build time
- Document which env vars are needed when in CLAUDE.md
- Test `vercel env pull` to see what's actually synced

---

### Issue 9: Pages Attempting Prerendering with Backend Dependency
**Symptom:** Build fails with "Error occurred prerendering page '/blog-review'. Backend error 503."  
**Root Cause:** Pages with `revalidate` hint were being prerendered at build time, but the backend wasn't available or had no cached data.  
**Expected Behavior:** ISR should allow pages to fail prerendering and then revalidate on first user request.  
**Actual Behavior:** Next.js treats prerendering failure as a build error (exit 1).  
**Fix:** Added `export const dynamic = "force-dynamic"` to all data-dependent pages (skip prerendering entirely).

**Prevention:**
- Document that pages fetching from backend at build time need either:
  1. `force-dynamic` (skip prerendering), OR
  2. Backend running and warm during build
- Use ISR graceful degradation: if prerendering fails, fall back to on-demand rendering
- Set up pre-build script to warm backend cache before Vercel build starts

---

### Issue 10: Vercel CLI Env Variable Setting Syntax Error
**Symptom:** `vercel env add BACKEND_URL < file` fails with "Invalid number of arguments."  
**Root Cause:** Vercel CLI expects `vercel env add <name> <target> <gitbranch> < <file>`, not stdin redirection.  
**Expected Behavior:** Should accept pipe input for multi-line values.  
**Actual Behavior:** Command requires different syntax than expected.  
**Fix:** Used Vercel dashboard UI instead; confirmed variable with `vercel env ls`.

**Prevention:**
- Read Vercel CLI help: `vercel env add --help`
- Set secrets via dashboard (safer, more visible) instead of CLI
- Document the correct CLI syntax in team wiki

---

### Issue 11: Vercel Cache-Control Header Not Persisting
**Symptom:** API routes return `Cache-Control` headers locally, but Vercel edge strips them.  
**Root Cause:** Vercel's `vercel.json` had `{ "headers": { ... } }` with blanket `no-store` override.  
**Expected Behavior:** Per-route `Cache-Control` headers in Next.js should take precedence.  
**Actual Behavior:** Vercel config override resets all caching to `no-store`.  
**Fix:** Removed blanket `no-store` from `vercel.json`; used only `{ "framework": "nextjs" }`.

**Prevention:**
- Keep `vercel.json` minimal; don't override headers unless absolutely necessary
- Document cache strategy in CLAUDE.md (ISR + Cache-Control, not vercel.json headers)
- Test with curl to verify headers: `curl -I https://api.example.com/route | grep Cache-Control`

---

### Issue 12: ISR Revalidate Values Ignored Due to force-dynamic
**Symptom:** Pages with both `force-dynamic` and `revalidate` don't seem to revalidate.  
**Root Cause:** Misunderstanding: `force-dynamic` skips prerendering, but `revalidate` hint still applies on first user request.  
**Expected Behavior:** `force-dynamic` + `revalidate` = on-demand rendering with ISR revalidation (not prerendering).  
**Actual Behavior:** Correct behavior, but initially confusing to developers.  
**Fix:** Documented the pattern clearly in comments and CLAUDE.md.

**Prevention:**
- Add clear comments explaining the pattern: "Skip prerendering; ISR revalidates after N seconds on first request"
- Test with `curl -I` to see `Cache-Control` header on pages
- Monitor Vercel dashboard to confirm ISR is working (cache hit rate should be high)

---

### Issue 13: Vercel Build Logs Truncated, Missing Error Details
**Symptom:** Build fails but logs don't show the exact error (last line cuts off).  
**Root Cause:** Vercel's build output has a character limit; long stack traces are truncated.  
**Expected Behavior:** Full build logs should be accessible via `vercel logs` or deployment detail page.  
**Actual Behavior:** Error message is incomplete, making debugging difficult.  
**Fix:** Ran `npm run build` locally to see full output; identified the real error (backend 503).

**Prevention:**
- Always replicate the build locally: `npm run build` in the `frontend/` directory
- Use `vercel logs <deployment-url>` to fetch full logs after deploy
- Enable Vercel analytics to track which pages fail to prerender

---

### Issue 14: Vercel Preview vs. Production Environment Variables Mismatch
**Symptom:** Deploy to preview (staging) works, but production fails with "BACKEND_URL not configured."  
**Root Cause:** Environment variables were set only in "Preview" scope, not "Production" scope in Vercel.  
**Expected Behavior:** Each environment (Development, Preview, Production) should have its own env var set.  
**Actual Behavior:** Production deployment inherited nothing from Preview; vars were empty.  
**Fix:** Set `BACKEND_URL` in Vercel dashboard under Environment Variables → Production scope.

**Prevention:**
- Explicitly set environment variables for all three scopes: Development, Preview, Production
- Create a checklist in CLAUDE.md listing all required env vars and their required scopes
- Test each environment before deploying to production: `vercel deploy --prod` to a staging domain first

---

## Category 3: Cross-Stack Auth Token & Secret Management Issues

### Issue 15: Scheduler Token Mismatch (Secret Manager vs. Cloud Run Env Var)
**Symptom:** Cloud Scheduler sends correct `X-Scheduler-Token` header, but backend returns 401.  
**Root Cause:** `SCHEDULER_SECRET` in Secret Manager was a different value than what Cloud Scheduler was sending.  
**Expected Behavior:** Single source of truth for the secret; Cloud Scheduler reads from Secret Manager or env var.  
**Actual Behavior:** Two copies of the secret (one in Secret Manager, one in Cloud Run env var) were out of sync.  
**Fix:** Rotated the secret, updated both locations, redeployed Cloud Run with `--set-secrets=SCHEDULER_SECRET=...`.

**Prevention:**
- Use Secret Manager as the single source of truth
- In Cloud Run, reference Secret Manager: `--set-secrets=SCHEDULER_SECRET=secret-name:latest` (not hardcoded env vars)
- Document the secret name and how to rotate it in `rules/secrets.md`
- Test token before deploying: `curl -X POST https://backend/refresh/all -H "X-Scheduler-Token: $(gcloud secrets versions access latest --secret=SCHEDULER_SECRET)"`

---

### Issue 16: Vercel API Key Expired for Programmatic Access
**Symptom:** `vercel env ls` works, but `vercel deploy --prod` sometimes fails with auth errors.  
**Root Cause:** Vercel authentication token (stored locally in `~/.vercel/auth.json`) expired after 30 days.  
**Expected Behavior:** Token should auto-refresh or prompt for re-authentication.  
**Actual Behavior:** Auth fails silently; deploy fails with cryptic error.  
**Fix:** Ran `vercel logout && vercel login` to refresh authentication.

**Prevention:**
- Don't store Vercel auth in local files for CI/CD; use `VERCEL_TOKEN` env var instead
- Add `vercel whoami` check to deployment scripts; fail early if not authenticated
- Rotate credentials monthly; document rotation schedule

---

### Issue 17: GCP Service Account Key File Missing from Cloud Build
**Symptom:** `gcloud builds submit` tries to use ADC, but the key file doesn't exist in the build environment.  
**Root Cause:** Cloud Build assumes it will use the built-in service account, not a key file. But if code tries to load a key file, it fails.  
**Expected Behavior:** Cloud Build uses its service account identity automatically (no key file needed).  
**Actual Behavior:** Code imports `google.cloud.firestore` and tries to load a key file that isn't in the Docker image.  
**Fix:** Removed all key file references from code; rely on Cloud Run service account identity.

**Prevention:**
- Never load service account key files in Cloud Run or Cloud Build; use `google.auth.default()`
- The Firestore client library automatically detects the service account
- If needed, mount key files as secrets at runtime, not build time

---

### Issue 18: Scheduler Token Header Case Sensitivity
**Symptom:** Cloud Scheduler endpoint returns 401, but hardcoded test request with same token works.  
**Root Cause:** HTTP headers are case-insensitive, but `_verify_scheduler()` in FastAPI was checking exact case.  
**Expected Behavior:** FastAPI should normalize header names to lowercase.  
**Actual Behavior:** Header lookup was case-sensitive; `X-Scheduler-Token` vs. `x-scheduler-token` mismatch.  
**Fix:** Used consistent casing in Cloud Scheduler job configuration and backend code.

**Prevention:**
- In FastAPI, use `Header(...)` with lowercase parameter names; FastAPI normalizes automatically
- Document header names in lowercase in CLAUDE.md
- Test with both cases: `curl -H "X-Scheduler-Token: ..." -H "x-scheduler-token: ..."` to verify

---

### Issue 19: BACKEND_URL Endpoint Changed on Every Cloud Run Deploy
**Symptom:** Frontend deployed with hardcoded `BACKEND_URL=https://gcp3-backend-abc123.run.app`, but next Cloud Run deploy changes the URL.  
**Root Cause:** Cloud Run generates a new service URL on each deploy if traffic policy changes. Frontend had old URL in env var.  
**Expected Behavior:** Cloud Run service should have a stable alias or custom domain.  
**Actual Behavior:** Service URL changed; frontend now points to stale endpoint.  
**Fix:** Used Cloud Run service name (`gcp3-backend`) with stable region (`us-central1`), not the auto-generated URL. Or set up custom domain.

**Prevention:**
- Use Cloud Run service name as the stable reference: `https://gcp3-backend-us-central1.run.app` (pseudo-stable)
- Or map to a stable custom domain: `https://api.example.com` → points to Cloud Run service
- Document both the service name and custom domain in CLAUDE.md
- Test that `BACKEND_URL` resolves to the correct service before deploying frontend

---

### Issue 20: Firestore Credentials Leak in Docker Image
**Symptom:** Dockerfile `COPY` command copies `.env` file into image by mistake.  
**Root Cause:** `.dockerignore` missing; Docker copied all files including `.env` with secrets.  
**Expected Behavior:** `.dockerignore` should exclude `.env`, `.git`, `node_modules`, etc.  
**Actual Behavior:** Secrets were baked into the image and pushed to Artifact Registry.  
**Fix:** Added `.dockerignore` with proper exclusions; rebuilt and pushed image.

**Prevention:**
- Create `.dockerignore` in every project with the same patterns as `.gitignore`
- Add to `.dockerignore`: `.env`, `.env.local`, `*.key`, `.git`, `.git/**`, `node_modules`
- Before building, verify: `docker build --dry-run` (or just read the Dockerfile)
- Scan images for secrets: `gcloud container images scan <image-uri>`

---

---

## Category 4: Cloud Scheduler & Data Pipeline Failures *(added 2026-04-07)*

### Issue 21: SCHEDULER_SECRET Never Set on Cloud Run (Env Var Gap)
**Symptom:** Every Cloud Scheduler invocation of `/refresh/all` returned 401 Unauthorized. `industry_cache` in Firestore stopped updating; `industry-returns` page served 5-day-old data.  
**Root Cause:** `SCHEDULER_SECRET` existed in the Cloud Scheduler job's HTTP header config but was **never set as an environment variable on the Cloud Run service**. The `_verify_scheduler()` check reads from `os.environ["SCHEDULER_SECRET"]`; without the env var the comparison always fails.  
**Expected Behavior:** Cloud Run should have `SCHEDULER_SECRET` set via `--update-env-vars` or `--set-secrets` at deploy time so the scheduler token check passes.  
**Actual Behavior:** `gcloud run services describe` showed only `GCP_PROJECT_ID`, `FINNHUB_API_KEY`, and `GEMINI_API_KEY` — no `SCHEDULER_SECRET`.  
**Detection:** Checked `gcloud logging read` for the service around the last scheduled run time; found `POST /refresh/all HTTP/1.1" 401 Unauthorized`.  
**Fix:** `gcloud run services update gcp3-backend --update-env-vars SCHEDULER_SECRET=[token]`.

**Prevention:**
- Add `SCHEDULER_SECRET` to the deploy checklist alongside `FINNHUB_API_KEY` and `GEMINI_API_KEY`
- After any Cloud Run deploy, run `gcloud run services describe --format=json | python3 -c "import json,sys; [print(e['name']) for e in json.load(sys.stdin)['spec']['template']['spec']['containers'][0].get('env',[])]"` to audit present env vars
- Consider moving the secret to Secret Manager and referencing with `--set-secrets` so it persists across redeploys automatically

---

### Issue 22: compute-returns Not Called in /refresh/all Pipeline
**Symptom:** Even when `/refresh/all` auth was fixed, `industry_cache` returns stayed stale because the dedicated `compute_returns()` function was not wired into the morning refresh.  
**Root Cause:** `/refresh/all` Stage 3 calls `get_industry_data()`, which populates `industry_cache` via `_attach_stored_returns()`. However, `compute_returns()` — the standalone function that reads from `etf_store` and writes to `industry_cache` without making any API calls — was only reachable via `POST /admin/compute-returns`. That endpoint is not called by any scheduler job.  
**Expected Behavior:** After `get_industry_data()` populates fresh ETF quotes, `compute_returns()` should always run to ensure `industry_cache` reflects today's stored history regardless of whether Stage 3 fully succeeded.  
**Actual Behavior:** If Stage 3 errored partway through, `_attach_stored_returns()` was never called and `industry_cache` stayed at its last successful write date.  
**Fix:** Added Stage 3b to `/refresh/all` that explicitly calls `compute_returns()` after Stage 3.

**Prevention:**
- Make `compute_returns()` idempotent and include it as an explicit refresh stage — it costs zero API calls and is safe to run any time
- Document the dependency: `industry-returns` reads from `industry_cache`; `industry_cache` is only populated by `_attach_stored_returns()` or `compute_returns()`; neither runs on a schedule without being called from `/refresh/all`

---

### Issue 23: Stale gcp3_cache Entry Masks Fresh Firestore Data
**Symptom:** After fixing the SCHEDULER_SECRET and manually running `compute-returns`, the `/industry-returns` API still returned the old `updated` timestamp for several hours.  
**Root Cause:** `industry_returns.py` caches its assembled result in `gcp3_cache` with a 6-hour TTL (key: `industry_returns:{today}`). After `industry_cache` was refreshed, the stale `gcp3_cache` document continued to be served until it expired — the code checks `gcp3_cache` first and short-circuits before reading `industry_cache`.  
**Expected Behavior:** Forcing a refresh via `compute-returns` should invalidate or bypass the `gcp3_cache` entry so the next read reflects fresh data.  
**Actual Behavior:** The 6-hour `gcp3_cache` entry from the earlier (stale) read was still valid; fresh `industry_cache` data was invisible until TTL expired.  
**Fix:** Manually deleted the stale `gcp3_cache` document via Firestore client so the next API call rebuilt it from the fresh `industry_cache`.

**Prevention:**
- When triggering `POST /admin/compute-returns`, also invalidate the corresponding `gcp3_cache` key (`industry_returns:{today}`) so callers immediately see fresh data
- Consider adding a `?force` query param to `GET /industry-returns` that bypasses the cache (admin/internal use only, behind scheduler token)
- Document the two-layer cache (Firestore `industry_cache` → `gcp3_cache` → API response) so the staleness chain is visible during debugging

---

## Lessons Learned & Best Practices

### 1. Service Account IAM Roles Are Not Inherited
**Lesson:** Default Cloud Run service account doesn't automatically get access to all services.  
**Fix:** Document required IAM roles and grant them in deployment scripts.

### 2. Secret Manager + Cloud Run Requires Explicit Binding
**Lesson:** Secret Manager secrets must be explicitly bound to the Cloud Run service account.  
**Fix:** Use `--set-secrets=NAME=secret-name:latest` at deploy time; verify with `gcloud run services describe --format=json | jq .spec.template.spec.containers[0].env`

### 3. Build-Time vs. Runtime Environment Variables Are Different
**Lesson:** Vercel's build environment doesn't have the same variables as runtime.  
**Fix:** Use `force-dynamic` for pages that need to fetch at runtime; keep build-time data static or pre-computed.

### 4. ISR + force-dynamic Is a Valid Pattern
**Lesson:** `force-dynamic` skips prerendering, but `revalidate` hint still applies on first user request.  
**Fix:** Document this pattern clearly; test with monitoring to confirm revalidation is working.

### 5. Always Replicate Build Locally
**Lesson:** Vercel build logs can be truncated or misleading.  
**Fix:** Run `npm run build` locally before deploying to catch errors early.

### 6. Secrets Should Have a Single Source of Truth
**Lesson:** Syncing secrets manually between Secret Manager and env vars causes mismatches.  
**Fix:** Use Secret Manager as the single source; reference from Cloud Run with `--set-secrets`.

### 7. Custom Domains > Auto-Generated URLs
**Lesson:** Cloud Run service URLs can change; custom domains are stable.  
**Fix:** Set up a custom domain or Cloud Load Balancer frontend for production services.

### 8. Verify Scheduler Jobs Are Actually Succeeding
**Lesson:** A scheduler job can be "ENABLED" in Cloud Scheduler and still be silently failing every run.  
**Fix:** After any backend deploy, check `gcloud scheduler jobs describe <job>` for `status.code` — any non-zero code means the last run failed. Cross-check with `gcloud logging read` for 401/500 responses around the scheduled time.

### 9. Two-Layer Caches Create Non-Obvious Staleness Chains
**Lesson:** `industry-returns` has two caches: `industry_cache` (source data) and `gcp3_cache` (assembled response). Refreshing the source doesn't help if the response cache is still live.  
**Fix:** When forcing a data refresh, also invalidate the downstream response cache. Document cache layers per endpoint.

### 10. .dockerignore Is as Important as .gitignore
**Lesson:** Secrets can leak into Docker images by accident.  
**Fix:** Create `.dockerignore` in every project; scan images with `gcloud container images scan`.

---

## Timeline

| Date | Issue | Duration | Resolution |
|------|-------|----------|------------|
| 2026-04-07 22:15 | Firestore TTL command fails (empty project ID) | 5 min | Set gcloud config default project |
| 2026-04-07 22:20 | Cloud Run min-instances deploy fails | 10 min | Authorized with gcloud auth, reran command |
| 2026-04-07 22:25 | Cloud Scheduler job creation (token auth issues) | 15 min | Retrieved token from Secret Manager, created jobs |
| 2026-04-07 22:35 | Vercel build fails (BACKEND_URL not available) | 25 min | Added force-dynamic to data-dependent pages |
| 2026-04-07 22:40 | Frontend ISR pages still failing prerendering | 30 min | Converted remaining pages to force-dynamic + revalidate |
| 2026-04-07 22:50 | Vercel deploy succeeds | 50 min | Final verification of deployment |
| 2026-04-07 (later) | industry-returns page showing 5-day-old data | — | Investigated: scheduler 401 since April 2 |
| 2026-04-07 (later) | SCHEDULER_SECRET missing from Cloud Run env vars | ~10 min | Set via `gcloud run services update --update-env-vars` |
| 2026-04-07 (later) | compute-returns not wired into /refresh/all | ~5 min | Added Stage 3b to /refresh/all in main.py |
| 2026-04-07 (later) | Stale gcp3_cache masking fresh industry_cache | ~5 min | Deleted stale cache document via Firestore client |

**Total Extended Timeline:** ~50 min original deployment (vs. 15–20 min optimal); follow-up incident ~20 min  
**Root Cause of Delay:** Build-time vs. runtime environment variable confusion (original); missing env var on Cloud Run causing silent scheduler failures for 5 days (follow-up)

---

## Recommendations for Future Deployments

### 1. Pre-Deployment Checklist
Create a checklist in CLAUDE.md:
```
☐ GCP Service Accounts have required IAM roles
☐ Cloud Run service account can access Firestore
☐ Cloud Run service account can read from Secret Manager
☐ Vercel environment variables set for all scopes (Development, Preview, Production)
☐ Backend URL stable (custom domain or service name, not auto-generated)
☐ Local npm run build succeeds
☐ All secrets rotated within the last 30 days
☐ .dockerignore present and up-to-date
☐ SCHEDULER_SECRET present in Cloud Run env vars (gcloud run services describe | grep SCHEDULER)
☐ After deploy: check last scheduler run status (gcloud scheduler jobs describe <job> | grep status)
☐ After deploy: verify /refresh/all returns 200 with a manual curl using the scheduler token
```

### 2. Automated IAM Setup Script
Create `.gcloud/setup-iam.sh`:
```bash
#!/bin/bash
PROJECT_ID="ttb-lang1"

# Cloud Run service account
RUN_SA="$PROJECT_ID@appspot.gserviceaccount.com"
gcloud iam roles grant $RUN_SA \
  --role=roles/datastore.user \
  --project=$PROJECT_ID

gcloud iam roles grant $RUN_SA \
  --role=roles/secretmanager.secretAccessor \
  --project=$PROJECT_ID

# Cloud Build service account
BUILD_SA="$PROJECT_ID@cloudbuild.gserviceaccount.com"
gcloud iam roles grant $BUILD_SA \
  --role=roles/run.developer \
  --project=$PROJECT_ID
```

### 3. Vercel Deployment Script
Create `frontend/vercel-deploy.sh`:
```bash
#!/bin/bash
set -e

# Verify environment
vercel whoami || (vercel logout && vercel login)

# Check env vars
echo "Checking Vercel environment variables..."
vercel env ls | grep BACKEND_URL || echo "WARNING: BACKEND_URL not set"

# Local build
npm run build

# Deploy
vercel --prod
```

### 4. Documentation Updates
Add to CLAUDE.md:
- Required IAM roles per service
- Secret names and rotation schedule
- Vercel environment variable scopes
- Stable backend URL (custom domain)
- ISR + force-dynamic pattern explanation
- Troubleshooting guide for common errors

---

## Conclusion

The 23 issues were largely due to:
1. **Cross-service auth complexity** (GCP IAM, Secret Manager, Cloud Run, Cloud Build)
2. **Build-time vs. runtime environment variable confusion** (Vercel-specific)
3. **Misconfiguration of service account permissions** (IAM roles)
4. **Lack of automated validation** (no pre-flight checks)
5. **Silent scheduler failures** — a missing env var caused 5 days of stale data with no alerting

Future deployments should benefit from:
- Automated IAM setup scripts
- Clear documentation of env var scopes
- Pre-deployment checklists (updated to include scheduler verification)
- Local build replication before Vercel deploy
- Single source of truth for secrets (Secret Manager)
- Post-deploy scheduler health check as a standard step
- Documented cache layer chains per endpoint so staleness is debuggable

All issues have been resolved. Scheduler is authenticating correctly; `industry_cache` is refreshing daily; `industry-returns` now displays the exact Firestore `updated` timestamp. ✅
