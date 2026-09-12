# Security & Correctness Review — 2026-07-11

Review of the current uncommitted working tree (`git diff HEAD`, 23 files,
~383 insertions) before deciding whether to deploy it to `gcp3-backend`.
Scope: `backend/main.py`, `backend/gemini_client.py`,
`backend/llm/provider_router.py`, `backend/llm/providers/openrouter.py`,
`backend/technical_signals.py`, `backend/cloudbuild.yaml`.

**Bottom line: do not deploy this working tree as-is.** Findings #1–#2 are a
live, unauthenticated path to another user's Stripe billing controls.
Findings #3–#4 mean the Stripe/LLM-fallback code would ship non-functional
even if the auth gap were fixed, because required secrets were never wired
into the Cloud Run deploy config.

---

## 🔴 Critical — blocks deploy

### 1. `POST /billing-portal` has no authentication
**File:** `backend/main.py:1750`

```python
@app.post("/billing-portal")
async def billing_portal(body: BillingPortalRequest):
    ...
    session = stripe.billing_portal.Session.create(
        customer=body.stripe_customer_id,
        return_url=body.return_url,
    )
```

`stripe_customer_id` comes straight from the request body. There is no Clerk
session check, no JWT verification, nothing tying the caller to that customer
ID anywhere in `main.py`.

**Impact (IDOR):** anyone who learns or guesses another user's Stripe
customer ID (leaked in a client log, a prior API response, shared support
ticket, etc.) can POST it here and receive a hosted Stripe portal URL with
full self-serve control over that person's subscription — view/download
invoices, change payment method, or **cancel the subscription**.

**Fix:** derive `stripe_customer_id` server-side from a verified Clerk
session (e.g. look it up from `/users/{clerk_user_id}/subscription/current`
after validating the caller's JWT), never trust it from the request body.

---

### 2. `POST /checkout-session` has no authentication
**File:** `backend/main.py:1651`

```python
class CheckoutRequest(BaseModel):
    clerk_user_id: str
    email: str
    ...

@app.post("/checkout-session")
async def create_checkout_session(body: CheckoutRequest):
    ...
    metadata={"clerk_user_id": body.clerk_user_id},
```

`clerk_user_id` is caller-supplied and never checked against an authenticated
session.

**Impact:** any client can create a Checkout session with
`metadata.clerk_user_id` set to an arbitrary account. When
`checkout.session.completed` fires, the webhook (finding below) activates a
paid subscription on that account attributed to a payment the account owner
never approved — confusing at minimum, abusable for account-state pollution
at worst (unlimited pending Checkout sessions tied to arbitrary user IDs).

**Fix:** same as #1 — derive `clerk_user_id` from a verified session, not the
request body.

---

## 🟠 High — deploy is broken even if auth is fixed

### 3. Stripe secrets never added to `cloudbuild.yaml`
**File:** `backend/cloudbuild.yaml:20` (`--set-secrets` line)

`main.py` reads `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
`STRIPE_PRICE_ID` via `os.getenv(...)`, but none appear in the Cloud Run
deploy's `--set-secrets`/`--set-env-vars` list. Verified by grep — zero
matches in `cloudbuild.yaml`.

**Impact:** as deployed, `stripe.api_key` is `""`. `/checkout-session` and
`/billing-portal` permanently return 503 (`"Stripe not configured"`), and any
real Stripe webhook hitting `/webhooks/stripe` gets a 500
(`"Webhook secret not configured"`) — Stripe will eventually disable the
webhook endpoint after enough failed deliveries.

**Fix:** add all three to `--set-secrets` (after creating them in Secret
Manager) before this code ships.

---

### 4. `OPENROUTER_API_KEY` also missing from `cloudbuild.yaml`
**File:** `backend/cloudbuild.yaml:20`

`gemini_client.py`'s new OpenRouter fallback (`_call_openrouter`) and
`llm/providers/openrouter.py`'s now-live (no longer placeholder)
implementation both require `OPENROUTER_API_KEY`. Not present in
`--set-secrets`.

**Impact:** the moment Mistral fails or rate-limits in production,
`call_gemini()` falls through to OpenRouter and immediately raises
`RuntimeError("OPENROUTER_API_KEY not set")` — the fallback the diff was
built to add silently can't fall back. Every caller (`ai_summary.py`,
`story_picker.py`, `daily_blog.py`, `blog_reviewer.py`,
`correlation_article.py`) loses its safety net.

**Fix:** add `OPENROUTER_API_KEY` to `--set-secrets`.

---

## 🟡 Medium

### 5. Bare `except Exception` retries non-retryable Mistral errors
**File:** `backend/gemini_client.py:141`

The retry loop around `_call_mistral()` catches `Exception` broadly,
including the immediate `RuntimeError("MISTRAL_KEY not set")` that used to
fail fast. That error is now retried 2 more times with 5s/10s backoff before
falling through to OpenRouter.

**Impact:** if `MISTRAL_KEY` is ever unset or invalid, every `call_gemini()`
call burns ~15s of pointless sleep before even attempting the fallback —
latency inflation on every LLM-backed endpoint, worse in combination with
finding #4 (no working fallback to land on anyway).

**Fix:** distinguish configuration errors (missing key) from transient
errors (429, timeout) and fail fast on the former.

---

### 6. `stripe_webhook` has no idempotency handling
**File:** `backend/main.py:1682`

No dedup on `event["id"]`. Stripe automatically retries any webhook that
doesn't return 2xx quickly.

**Impact:** currently low-risk because `checkout.session.completed` uses
Firestore `.set()` (overwrite-safe), but this pattern breaks silently the
moment a non-idempotent handler is added (e.g. crediting usage on
`invoice.paid`) without a dedup guard.

**Fix:** check/store `event["id"]` in Firestore before processing, skip if
already seen.

---

### 7. `checkout.session.completed` silently no-ops without `clerk_user_id`
**File:** `backend/main.py:1707`

```python
if clerk_user_id:
    firestore_db().collection("users")...
```

No `else` branch — no log, no error.

**Impact:** if `/checkout-session` is ever called without `clerk_user_id`
(client bug, or a session created manually in the Stripe dashboard), Stripe
charges the customer and considers the subscription active, but no Firestore
entitlement doc is ever created. The user pays; the app doesn't know.

**Fix:** log a warning (or alert) when `clerk_user_id` is missing on a
completed checkout.

---

### 8. `_verify_zo_secret` uses non-constant-time comparison
**File:** `backend/main.py:553` (mine — introduced in this diff)

```python
bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
if bearer != expected:
```

Plain `!=` string comparison is not constant-time; separately,
`removeprefix` silently no-ops if the header lacks the `"Bearer "` prefix
rather than rejecting it outright.

**Impact:** low in practice (internal shared secret between Zo and GCP3, not
a globally exposed high-value credential), but cheap to fix correctly.

**Fix:** `hmac.compare_digest(bearer, expected)`, and reject if the header
didn't actually start with `"Bearer "`.

---

## 🟢 Low / cleanup

### 9. Duplicate OpenRouter client implementations
**Files:** `backend/gemini_client.py` (`_call_openrouter`) and
`backend/llm/providers/openrouter.py` (`OpenRouterProvider.call`)

Same URL, same model constant, same markdown-fence-stripping logic,
implemented twice with slightly different payload shapes. Will drift.

**Fix:** extract a shared `_call_openrouter_raw()` helper, or have
`gemini_client.py` call `OpenRouterProvider` directly.

### 10. Copy-pasted subscription lookup in `stripe_webhook`
**File:** `backend/main.py:1717-1735`

`customer.subscription.updated` and `customer.subscription.deleted` branches
duplicate the same `collection_group("subscription").where("stripe_customer_id", ...)`
query, differing only in the status value written.

**Fix:** extract `_update_subscription_by_customer(customer_id, updates: dict)`.

### 11. Dead code
- `backend/gemini_client.py:15` — `import json as _json`, never used.
- `backend/technical_signals.py:22-24` — `ENGINE_VERSION` constant written
  into every scored row, no consumer reads it.

### 12. `gemini_client.py` duplicates `provider_router.py`'s retry/fallback engine
`call_gemini()` hand-rolls retry + backoff + fallback chaining that
`structured_llm_call()` (provider_router.py + circuit_breaker.py) already
provides generically. Two independent LLM-call engines now exist in this
backend for "raw text" vs. "structured" callers — bugfixes to one won't
propagate to the other. Not urgent, but worth consolidating.

### 13. `zo_enrichment` TTL duplicates `firestore.py`'s existing pattern
**File:** `backend/main.py:373-374`

`firestore.py` already has `set_cache(key, value, ttl_hours/ttl_seconds)`
centralizing the `expires_at` computation. The new `/api/zo-hydrate` route
reimplements the same TTL pattern inline instead of extending `set_cache` to
support arbitrary collections. *(Note: the TTL policy itself — the
`gcloud firestore fields ttls update` — has already been applied live for
`zo_enrichment.expires_at`, confirmed `ACTIVE` in Firestore. This finding is
about code duplication, not a missing TTL.)*

---

## What's actually safe to ship

The two files this review's author added are not implicated in any of the
above:

- `backend/main.py` — `ZoHydrationPayload`, `GET /api/nwf-digest`,
  `POST /api/zo-hydrate`, `_verify_zo_secret` (finding #8 only, minor)
- `backend/cloudbuild.yaml` — `--cpu-boost`, `ZO_HYDRATE_SECRET` in
  `--set-secrets`
- `backend/.gcloudignore` — new file, build hygiene only

These were reviewed as part of the same diff and have no findings beyond #8.

## Recommended path

1. Do **not** deploy the Stripe endpoints or the `gemini_client.py`/
   `provider_router.py` LLM changes until #1–#4 are fixed.
2. `git stash` those files, deploy only the Zo-hydration + `.gcloudignore` +
   `--cpu-boost` changes.
3. Fix #1–#2 (add Clerk session verification to both Stripe routes) and #3–#4
   (add the missing secrets to `cloudbuild.yaml` + Secret Manager) as a
   separate, dedicated PR before that code goes live.
