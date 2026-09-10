# nu1: signal-quality-and-provenance status update

Date: 2026-07-09

## Where things stand

**Important finding: step 1 is already done.** The `feat/signal-provenance-staleness`
branch's commit (`77fddf9` — "fix: stamp engine_version + fix stale updated timestamp
in /signals") was already merged into `main` via PR #72, landing as `4d870df`
("fix: stamp engine_version + fix stale updated timestamp in /signals (#72)").

Verified on `origin/main` (`backend/technical_signals.py`):
- `ENGINE_VERSION = "technical_signals@1.0.0"` constant exists near the top of the file.
- `_score_etf()` stamps `"engine_version": ENGINE_VERSION` into every scored signal dict.
- The single-ticker path (`elif symbol:` branch in `get_technical_signals()`) now
  includes `"updated": returns_data.get("updated")`, matching the all-tickers path —
  the staleness-detection gap is fixed.

So there is **no cherry-pick to do** — `git merge-base --is-ancestor
feat/signal-provenance-staleness origin/main` returns false (different commit hash,
likely squash-merged), but the file content is identical/already present. The
`feat/signal-provenance-staleness` branch is superseded and safe to delete once this
is confirmed — **recommend deleting it** (both local and `origin/feat/signal-provenance-staleness`)
since its only commit already shipped via PR #72.

## What's still open (step 2 + 3 — not started)

1. Add `data_quality_score` field to `/signals` response.
   - Need to locate `@app.get("/signals")` in `backend/main.py` (not yet inspected —
     the local checkout's `backend/main.py` has unrelated uncommitted changes from
     branch `fix/pipeline-data-source-degradation-v2`, so inspection should be done
     against `origin/main` or a fresh branch off `main`, not the dirty working tree).
   - Need to check `backend/data_client.py` and the debug_status endpoint
     (~line 128-200 per task notes) for an existing freshness-check pattern to mirror
     — not yet located/confirmed in this session.
   - Should be a cheap, additive float [0,1] or enum ("fresh"/"stale"/"unknown")
     derived from the existing `updated` timestamp already returned by `/signals`.
2. Test: check `backend/tests/` (or similar) for existing `/signals` coverage; add a
   minimal test for the new field if infra exists, skip otherwise.
3. Commit (message ending `Co-Authored-By: Claude <noreply@anthropic.com>`), push,
   open PR against `main` via `gh pr create`, explaining standalone that it includes
   the (already-shipped-but-re-noted) provenance/staleness fix context plus the new
   `data_quality_score` field.

## Repo hygiene note

The local `~/code/gcp3` working tree (on branch `fix/pipeline-data-source-degradation-v2`)
has significant uncommitted changes across `backend/main.py`, `backend/gemini_client.py`,
`backend/llm/*`, `backend/technical_signals.py`, and much of `frontend/`. Any new branch
for this task should be created fresh off `main`/`origin/main` (e.g. via a clean clone or
`git worktree`) rather than branching from the current dirty checkout, to avoid dragging
in unrelated changes.

## Recommended next steps (for remote continuation)

1. `git fetch origin && git checkout -b feat/signal-quality-score origin/main`
   (clean branch, no cherry-pick needed since provenance/staleness is already in main).
2. Locate `@app.get("/signals")` / `def signals(...)` in `backend/main.py` on this new
   branch, and the freshness pattern in `debug_status` (~line 128-200) /
   `backend/data_client.py`.
3. Add `data_quality_score` (or fresh/stale/unknown enum) computed from `updated`,
   reusing the existing staleness threshold constant if one exists — do not invent a
   new pipeline.
4. Add a minimal test only if `/signals` test coverage already exists.
5. Commit, push, `gh pr create` against `main`.
6. Delete `feat/signal-provenance-staleness` (local + remote) since PR #72 already
   shipped its content.
