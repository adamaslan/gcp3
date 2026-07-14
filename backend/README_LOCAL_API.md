# Running the GCP3 Finance API locally (no GCP)

The API can run on a laptop with **no GCP project, no Firestore, and no service
account** — the cache is backed by a local SQLite file instead.

## Quick start

```bash
cd backend
cp .env.local.example .env      # then fill FINNHUB_API_KEY (see below)
./run_local.sh                  # → http://localhost:8080  (docs at /docs)
```

That's it. `run_local.sh` sets `CACHE_BACKEND=sqlite` and starts uvicorn via
`main.py`'s `__main__` block.

## How it works

`firestore.py::db()` and `data_client.py::_fs()` switch on the `CACHE_BACKEND`
env var:

- `firestore` (default) — real Firestore, prod behavior, unchanged.
- `sqlite` — `local_firestore.py`, a SQLite-backed shim implementing the exact
  slice of the Firestore client these modules use (`collection().document().get/
  set/delete` and the one id-range `where/order_by/limit/stream` query). One file
  (`LOCAL_CACHE_DB`, default `./local_cache.db`), one table.

No other code changes: every cache function still calls `db().collection(...)`.
Endpoints that need the raw Firestore admin client for features with no local
analog degrade gracefully (e.g. the AlphaVantage cross-instance call counter is
simply not tracked locally).

## Pointing the portal / mobile app at your local backend

- Portal: set `MCP_BACKEND_URL=http://localhost:8080` in `nuwrrrld-portal/.env.local`
- Mobile: set `EXPO_PUBLIC_GCP3_URL=http://localhost:8080`

## Keys

Market-data keys are read from the environment or `backend/.env`. `FINNHUB_API_KEY`
is the main one; missing optional sources (AlphaVantage, OpenRouter) degrade
gracefully. Do **not** set `GCP_PROJECT_ID` for a pure-local run — `CACHE_BACKEND`
takes precedence regardless, but leaving it unset proves no Firestore path is hit.
