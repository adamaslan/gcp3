"""Shared helpers for the 7-tool backtests.

Each backtest pulls (a) what the deployed backend currently reports for a
tool, (b) the same data freshly from yfinance / Finnhub, and (c) writes
the deltas to a per-tool JSON report so the markdown writer can summarize
them in one place.

Run from `backend/` with `fin-ai1` mamba env active.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger("backtest")

BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def _require_backend_url() -> str:
    """Resolve BACKEND_URL lazily so import never blocks on env state."""
    if BACKEND_URL:
        return BACKEND_URL
    raise RuntimeError(
        "Set BACKEND_URL env var before running backtests, e.g.\n"
        "  export BACKEND_URL=$(gcloud run services describe gcp3-backend "
        "--region us-central1 --format='value(status.url)')"
    )


def finnhub_key() -> str:
    """Pull the Finnhub key from Secret Manager (read-only, never logged).

    Falls back to gcloud-managed secret if FINNHUB_API_KEY env var is unset.
    GCP_PROJECT_ID must be set so the gcloud invocation is reproducible
    across environments rather than hard-coded to a single project.
    """
    key = os.environ.get("FINNHUB_API_KEY")
    if key:
        return key
    project = os.environ.get("GCP_PROJECT_ID")
    if not project:
        raise RuntimeError(
            "FINNHUB_API_KEY not set and GCP_PROJECT_ID not set — cannot fetch "
            "secret from Secret Manager. Export one or the other."
        )
    result = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         "--secret=FINNHUB_API_KEY", f"--project={project}"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def fetch_backend(path: str) -> dict[str, Any]:
    """GET a JSON endpoint from the live backend. Raises on non-2xx."""
    url = _require_backend_url()
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{url}{path}")
        r.raise_for_status()
        return r.json()


def fetch_yf_history(symbols: list[str], days: int = 7) -> dict[str, pd.DataFrame]:
    """Fetch last `days` of daily adj-close for each symbol via yfinance.

    Returns a dict keyed by symbol; missing symbols are omitted with a warning.
    """
    import yfinance as yf
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 5)  # buffer for non-trading days
    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            df = yf.download(sym, start=start, end=end, progress=False, auto_adjust=False)
            if df.empty:
                logger.warning("yfinance: empty for %s", sym)
                continue
            # Flatten the column MultiIndex yfinance returns ({field}, {sym})
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            out[sym] = df.tail(days)
        except Exception as exc:
            logger.warning("yfinance: %s failed: %s", sym, exc)
    return out


def fetch_finnhub_quote(client: httpx.Client, symbol: str, api_key: str) -> dict:
    """One Finnhub /quote call. Returns {} on failure (caller decides severity)."""
    try:
        r = client.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol, "token": api_key},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("finnhub: %s failed: %s", symbol, exc)
        return {}


def pct_delta(a: float | None, b: float | None) -> float | None:
    """Return |a - b| / |b| as a percentage, or None if either side missing."""
    if a is None or b is None or b == 0:
        return None
    return round(abs(a - b) / abs(b) * 100, 3)


def write_report(name: str, payload: dict[str, Any]) -> Path:
    """Write a backtest report to reports/{name}_{today}.json."""
    path = REPORTS_DIR / f"{name}_{date.today()}.json"
    payload["_meta"] = {
        "tool": name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  wrote {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
    return path


def summarize(report: dict[str, Any]) -> str:
    """Produce a one-line summary for the markdown writer to embed."""
    matches = report.get("matches", 0)
    mismatches = report.get("mismatches", 0)
    skipped = report.get("skipped", 0)
    return f"{matches} match · {mismatches} mismatch · {skipped} skipped"
