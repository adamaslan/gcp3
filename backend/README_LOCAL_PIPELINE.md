# NuWrrrld Local Pipeline Execution

Run the daily signal generation and AI analysis locally, syncing results to Firebase.

## Quick Start

### 1. Install dependencies
```bash
cd /Users/adamaslan/code/gcp3/backend
pip install google-cloud-firestore python-dotenv httpx
```

### 2. Validate configuration
All API keys are automatically loaded from:
- `/Users/adamaslan/code/homebase/.env`
- `/Users/adamaslan/code/gcp3/backend/.env`

Check they're loaded:
```bash
python local_config.py
```

Expected output:
```
Configuration loaded:
  mistral_key                    ✓ <redacted>
  openrouter_key                 ✓ <redacted>
  finnhub_key                    ✓ <redacted>
  ...
✅ All required keys configured
```

### 3. Run the pipeline (with Firebase sync)

#### Option A: On Cloud Run (automatic auth)
Cloud Run instances have built-in authentication. Just run:
```bash
export GCP_PROJECT_ID=nuwrrrld-prod
python firebase_sync.py
```

#### Option B: Locally with service account key
If you have a GCP service account JSON key:
```bash
export GCP_PROJECT_ID=nuwrrrld-prod
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
python firebase_sync.py
```

To get a service account key:
1. Go to [GCP Console](https://console.cloud.google.com) → IAM & Admin → Service Accounts
2. Create or select a service account with Firestore Editor role
3. Create a JSON key and download it
4. Keep it secure (never commit to Git!)

#### Option C: Emulate Firestore locally (for testing)
If you want to test without touching production Firestore:
```bash
# Start the Firestore emulator (requires gcloud CLI)
gcloud beta emulators firestore start

# In another terminal:
export FIRESTORE_EMULATOR_HOST=localhost:8081
export GCP_PROJECT_ID=nuwrrrld-prod
python firebase_sync.py
```

### 4. Run for a specific date

```bash
python firebase_sync.py --date 2026-06-25
```

## What Gets Synced

The pipeline syncs these collections to Firestore:

| Stage | Collection | Document ID | Data |
|-------|------------|-------------|------|
| Technical signals | `gcp3_cache` | `technical_signals:all:2026-06-25` | 262 signals for 54 ETFs |
| AI summary | `gcp3_cache` | `ai_summary:2026-06-25` | Market brief (2–3 paragraphs) |
| Sector rotation | `gcp3_cache` | `sector_rotation:2026-06-25` | Leaders/laggards (11 sectors) |
| Macro pulse | `gcp3_cache` | `macro_pulse:2026-06-25` | VIX, bonds, dollar, commodities |
| Morning brief | `gcp3_cache` | `morning_brief:2026-06-25` | Pre-market snapshot |

Each document includes:
- `key`: Document ID
- `value`: The actual data (dict or list)
- `updated_at`: ISO timestamp when written
- `expires_at`: ISO timestamp (24h from now by default)

## API Keys Used

| Key | Service | Loaded From |
|-----|---------|-------------|
| `MISTRAL_KEY` | LLM (primary) | `homebase/.env` |
| `OPENROUTER_API_KEY` | LLM (fallback) | `gcp3/backend/.env` |
| `FINNHUB_API_KEY2` | Market data | `homebase/.env` |

## Troubleshooting

### "MISTRAL_KEY not set"
- Check that `MISTRAL_KEY=...` is in `/Users/adamaslan/code/homebase/.env`
- Run `python local_config.py` to verify it's loaded

### "GCP_PROJECT_ID not configured"
- Set `export GCP_PROJECT_ID=nuwrrrld-prod` before running
- Or add `GCP_PROJECT_ID=nuwrrrld-prod` to `.env`

### "GOOGLE_APPLICATION_CREDENTIALS not set"
- You're running locally without a service account key (expected for Cloud Run)
- Either:
  1. Get a service account key (see above)
  2. Use Firestore emulator for testing
  3. Run this script ON Cloud Run where auth is automatic

### Firebase writes are slow
- First run caches data for 24h. Subsequent runs return cached results instantly.
- Clear cache manually with: `db.collection("gcp3_cache").document(key).delete()`

## Advanced: Running just one stage

```python
import asyncio
from technical_signals import get_technical_signals

result = asyncio.run(get_technical_signals())
print(f"Generated {len(result)} signals")
```

Or use the sync functions individually:
```python
import asyncio
from firebase_sync import sync_technical_signals

result = asyncio.run(sync_technical_signals())
print(result)
```

## Integration with Cloud Scheduler — not built yet

This section previously described a `nuwrrrld-daily-pipeline` Cloud Scheduler
job calling a `/refresh/daily` endpoint. **Neither exists.** Verified against
the live project (`gcloud scheduler jobs list --project=ttb-lang1`): no job
named `nuwrrrld-daily-pipeline` exists (the real jobs are all `gcp3-*`
prefixed, e.g. `gcp3-ai-summary-refresh`, `gcp3-premarket-warmup`), and
`backend/main.py` has no `/refresh/daily` route — `run_full_pipeline()`
(`firebase_sync.py`) is CLI-only (`python firebase_sync.py [--date YYYY-MM-DD]`),
never called over HTTP. The service account referenced
(`nuwrrrld-scheduler@nuwrrrld-prod.iam.gserviceaccount.com`) also names a
different GCP project (`nuwrrrld-prod`) than the one this backend actually
runs in (`ttb-lang1`), another sign this section documented a plan rather
than a deployed state.

Until this integration is actually built, run this pipeline **locally, by
hand** (the "Quick Start" above), or via `python firebase_sync.py`'s CLI
directly.

## Files

- **local_config.py** — Load API keys from both .env files
- **firebase_sync.py** — Run pipeline stages and sync to Firestore
- **nuwrrrld-pipeline.html** — Visual documentation of the full pipeline

## Next Steps

After syncing, the data is available via:
- **Local REST API**: `GET http://localhost:8000/signals`, `/content`, etc.
- **Frontend (app + portal)**: Reads from Firestore automatically
- **Custom queries**: Direct Firestore reads with proper TTL handling
