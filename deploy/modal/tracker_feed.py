"""Modal feed for the industry tracker: third independent path into Firestore.

Runs backend/feed_tracker.py (seed -> compute_returns -> freshness check) on a
weekday cron, writing straight to Firestore. It does not call the Cloud Run
backend, so it survives that service being down.

Schedule: 23:30 UTC weekdays, after Cloud Scheduler (22:00) and GitHub Actions
(23:00), so a vendor problem is not hit by all three at once.

Deploy (one-time), from the repo root:
    pip install modal
    modal token new
    modal secret create gcp3-tracker-feed \
        GCP_PROJECT_ID=ttb-lang1 \
        GCP_SA_KEY_JSON="$(cat /path/to/service-account.json)"
    modal deploy deploy/modal/tracker_feed.py

Run once now (bypasses the cron):
    modal run deploy/modal/tracker_feed.py
    modal run deploy/modal/tracker_feed.py --check-only
"""
import json
import os
import subprocess
import sys

import modal

app = modal.App("gcp3-tracker-feed")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REMOTE_BACKEND = "/root/backend"

# Same pins as backend/requirements.txt for the packages the feed imports.
# Only the seed path is needed, so the API and billing dependencies stay out.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "httpx==0.28.0",
        "google-cloud-firestore==2.19.0",
        "google-auth==2.40.3",
        "yfinance==0.2.54",
        "pandas>=2.0.0,<3.0.0",
        "numpy>=1.26.0,<3.0.0",
        "PyYAML>=6.0.0,<7.0.0",
        "pyarrow>=17.0.0,<19.0.0",
    )
    .add_local_dir(os.path.join(REPO_ROOT, "backend"), REMOTE_BACKEND, ignore=["__pycache__", "tests", "*.db"])
)

_SECRET = modal.Secret.from_name("gcp3-tracker-feed")


def _run_feed(check_only: bool) -> int:
    key_json = os.environ.get("GCP_SA_KEY_JSON", "")
    if not key_json or not os.environ.get("GCP_PROJECT_ID"):
        raise RuntimeError("GCP_SA_KEY_JSON and GCP_PROJECT_ID must be set in the gcp3-tracker-feed secret")
    json.loads(key_json)  # fail here with a clear error if the secret is malformed
    key_path = "/tmp/sa.json"
    with open(key_path, "w", opener=lambda p, f: os.open(p, f, 0o600)) as fh:
        fh.write(key_json)
    env = {**os.environ, "GOOGLE_APPLICATION_CREDENTIALS": key_path}
    args = [sys.executable, "feed_tracker.py"] + (["--check-only"] if check_only else [])
    try:
        return subprocess.run(args, cwd=REMOTE_BACKEND, env=env).returncode
    finally:
        os.remove(key_path)


@app.function(
    image=image,
    secrets=[_SECRET],
    schedule=modal.Cron("30 23 * * 1-5"),
    timeout=20 * 60,
    retries=modal.Retries(max_retries=1, initial_delay=60.0),
)
def feed(check_only: bool = False) -> None:
    code = _run_feed(check_only)
    if code != 0:
        raise RuntimeError(f"feed_tracker exited {code}: tracker stale or seed failed")


@app.local_entrypoint()
def main(check_only: bool = False) -> None:
    feed.remote(check_only)
