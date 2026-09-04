# Correction to the OpenRouter-migration plan's gcp3 audit

**Source plan:** `nuwrrrld-portal/docs/openrouter-migration-and-db-parity-plan.md`
(this repo doesn't carry its own copy). That plan's §0.1 audit table says:

> gcp3 backend: Mostly OpenRouter + Mistral... `GeminiProvider` is a stub that
> raises... Residual: `sector_rotation.py:76` still reads `GEMINI_API_KEY`
> directly... ~7 modules still `import call_gemini from gemini_client` —
> naming/debt, not live Gemini traffic.
>
> **Net:** the portal is done. The real migration surface is gcp3 backend
> (one live `GEMINI_API_KEY` path + naming debt).

That's wrong on two counts, found while implementing Phases 1-4 against the
actual code rather than the audit's description of it.

## What the audit got wrong

1. **`gemini_client.py`'s `call_gemini()` was live Gemini traffic, not naming
   debt.** Its docstring said "Gemini 2.0 Flash with Mistral fallback," and
   the implementation matched — Gemini primary, Mistral only on 3x 429. Every
   one of its 5 importers (`story_picker.py`, `ai_summary.py`,
   `correlation_article.py`, `blog_reviewer.py`, `daily_blog.py`) made a real
   `generativelanguage.googleapis.com` call on every run generating content.
   **Fixed in this PR** — see below.
2. **`llm/provider_router.py`'s `structured_llm_call()` — the thing Phase 1
   asks `sector_rotation.py` to route through — has no callers anywhere in
   this repo, and its `OpenRouterProvider` is an unimplemented stub** (raises
   unconditionally per its own docstring: "Network calls are intentionally
   not made"). Worse: `provider_router.py` wraps *every* provider name in
   `DisabledProvider` regardless of which provider it is — so even if
   `OpenRouterProvider` were implemented, the router would never reach it.
   The entire gateway always degrades to `ai_degraded=True`. **Fixed in this
   PR** for the free-text case (see below); the schema-validated gateway
   itself is a separate, larger task — see "Not fixed" below.

## What else the audit missed entirely

Two more live Gemini surfaces the audit's grep apparently never found,
because they don't reference `GEMINI_API_KEY` as an env var — they use the
`google-generativeai` SDK directly, which reads its own credential
convention:

- **`llm/structured_call.py`**'s `structured_generate()` — a 3-tier
  structured-output wrapper (native constrained decoding via
  `response_schema`, then a validation-error retry, then rule-based
  fallback). Called by `signals/multi_timeframe.py`, which is live in the
  signal-generation path.
- **`llm/grounded_call.py`** — wraps Gemini's Google Search grounding
  (`tools=[{"google_search_retrieval": {}}]`) for citation-backed output.

## What this PR actually fixes (Phases 1-3, revised scope)

- `sector_rotation.py`, `gemini_client.py` → `llm/legacy_client.py`, and all
  5 `call_gemini` importers now go through `call_llm()`: OpenRouter (a
  static free-model chain) primary, Mistral fallback. `gemini_client.py`
  survives as a one-release compat shim per the plan's own Phase 2
  instruction.
- `DEFAULT_LLM_PROVIDER_ORDER` drops `"gemini"` (now
  `["openrouter_qwen3", "mistral"]`), and `llm/providers/gemini.py` is
  deleted, since nothing calls the dead `structured_llm_call()` gateway that
  referenced it.
- `tests/conftest.py`'s env stub swapped `GEMINI_API_KEY` → `OPENROUTER_API_KEY`.

`grep -rn "GEMINI_API_KEY" backend/` now returns only this doc and
`llm/legacy_client.py`'s own explanatory docstring — Phase 1's original
"Done when" criterion — but that criterion undersold the actual remaining
surface, per the "Not fixed" section below.

## Not fixed here — needs its own plan

`llm/structured_call.py` and `llm/grounded_call.py` are a materially
different, larger migration than Phases 1-3's free-text case:

- **Constrained JSON decoding** (`response_schema` in the Gemini SDK) has no
  direct OpenRouter equivalent across every model in a free-tier chain —
  some free models support OpenAI-style `response_format: json_schema`,
  others don't, so the tier-1/tier-2 design (native decode → retry-with-error
  → rule-based) would need re-validating per model, not swapped 1:1.
- **Google Search grounding** (`google_search_retrieval`) is a
  Gemini-specific capability. The closest OpenRouter equivalent is a
  `:online` model suffix (web-search-augmented completion via a different
  mechanism) or a dedicated search-augmented model — not a drop-in
  replacement, and citation-format parity (`grounded_call.py`'s citation
  extraction) would need rebuilding against whatever that surface returns.
- Both feed `signals/multi_timeframe.py`, a live signal-generation path —
  higher blast radius than the free-text content generators Phases 1-3
  touched, and worth its own reviewed PR with real model-behavior testing
  rather than folding into this one.

Recommendation: treat this as **Phase 1.5** in the source plan (inserted
before Phase 4, which is itself partly blocked on it — `llm/pricing.py`'s
`MODEL_PRICING` and `llm/cost_logger.py` are keyed on Gemini model IDs
specifically because `structured_call.py` still calls Gemini; rewriting
those tables to OpenRouter IDs now, before that call is replaced, would just
break `compute_cost_usd()`'s lookup for the one remaining live Gemini path).
Phase 4 as originally scoped is deferred until Phase 1.5 lands.

## Phase 9 ("local == Firestore emulator") is superseded by open PR #76

The source plan's Phase 9 asks for `firestore.py::db()` to detect
`FIRESTORE_EMULATOR_HOST` and route local runs to the Firestore emulator.
**PR #76** (`feat: run the backend locally with no GCP (CACHE_BACKEND=sqlite)`)
already solves the same problem — a local run with no GCP project, no
Firestore, no service account — with a different, arguably better mechanism:
a `local_firestore.py` SQLite shim implementing the exact `collection().
document().get/set/delete` + range-query surface `firestore.py` and
`data_client.py` actually use, switched on `CACHE_BACKEND=sqlite`. It needs
no Java/firebase-tools emulator install, and its own test plan already
covers cache round-trips, TTL expiry, and a full FastAPI boot under the
local backend.

This PR does not duplicate that work — an emulator-detection branch and a
`CACHE_BACKEND` switch both modify `db()`'s body, and shipping both would
conflict for no benefit once PR #76 merges. **Recommendation: merge PR #76
as Phase 9's "local" answer; this PR only adds Phase 9's "backup" half**
(`scripts/export_firestore_backup.py` — see below), which PR #76 doesn't
touch. Rebase this PR onto `main` after PR #76 merges if the two ever
develop a real file conflict (currently they don't — `export_firestore_backup.py`
is a new file, unrelated to PR #76's diff).
