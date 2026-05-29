"""Industry Tracker: ETF performance across industries.

Data resolution chain per ETF:
  1. Finnhub — real-time intraday quote (primary)
  2. yfinance — free fallback when Finnhub fails (no quota)
  3. Alpha Vantage ANALYTICS_FIXED_WINDOW — batched (5 symbols/call),
     enriches valid quotes with multi-period returns (1m, 3m, 1y)
     when AV quota allows; pure bonus data, never blocks quotes

Permanent storage (etf_store):
  - On first run, seeds full price history for all ETFs via yfinance
  - Daily refresh appends only new trading days (delta fetch)
  - Multi-period returns calculated from stored history (zero API calls)
  - Populates industry_cache collection consumed by industry_returns.py
"""
import asyncio
import logging
from datetime import date, datetime, timezone, timedelta
from math import floor
import time

_EST = timezone(timedelta(hours=-5))


def _now_est_iso() -> str:
    """Return current time as an EST ISO string, e.g. '2026-04-25T09:32:00-05:00'."""
    return datetime.now(_EST).isoformat()

import httpx
import pandas as pd

from data_client import (
    av_analytics_batch,
    av_remaining_calls,
    get_cache,
    get_quote,
    set_cache,
)
from data_client import get_finnhub_metrics
import etf_store

logger = logging.getLogger(__name__)

_FIRESTORE_BATCH_MAX_OPS = 450  # stay under Firestore's 500-op batch limit
_QUOTE_CACHE_TTL_SECONDS = 60  # re-fetch Finnhub at most once per minute

# Lazy-initialized semaphores: module-level asyncio.Semaphore() binds to
# whatever event loop is running at import time, which may not be the loop
# that actually services requests (FastAPI creates its own loop on startup).
_INDUSTRY_LOCK: asyncio.Semaphore | None = None
_QUOTES_LOCK: asyncio.Semaphore | None = None
_ETF_FETCH_SEMAPHORE: asyncio.Semaphore | None = None


def _industry_lock() -> asyncio.Semaphore:
    global _INDUSTRY_LOCK
    if _INDUSTRY_LOCK is None:
        _INDUSTRY_LOCK = asyncio.Semaphore(1)
    return _INDUSTRY_LOCK


def _quotes_lock() -> asyncio.Semaphore:
    global _QUOTES_LOCK
    if _QUOTES_LOCK is None:
        _QUOTES_LOCK = asyncio.Semaphore(1)
    return _QUOTES_LOCK


def _etf_fetch_semaphore() -> asyncio.Semaphore:
    global _ETF_FETCH_SEMAPHORE
    if _ETF_FETCH_SEMAPHORE is None:
        _ETF_FETCH_SEMAPHORE = asyncio.Semaphore(8)
    return _ETF_FETCH_SEMAPHORE

# Industries → ETF, organized by sector group
INDUSTRIES: dict[str, dict[str, str]] = {
    "Technology": {
        "Software": "IGV",
        "Semiconductors": "SOXX",
        "Cloud Computing": "CLOU",
        "Cybersecurity": "HACK",
        "Artificial Intelligence": "BOTZ",
        "Internet": "FDN",
        "Hardware": "XLK",
        "Telecommunications": "VOX",
    },
    "Healthcare": {
        "Biotechnology": "IBB",
        "Pharmaceuticals": "XPH",
        "Healthcare Providers": "IHF",
        "Medical Devices": "IHI",
        "Managed Care": "XLV",
        "Healthcare REIT": "VHT",
    },
    "Financials": {
        "Banks": "KBE",
        "Insurance": "KIE",
        "Asset Management": "PFM",
        "Fintech": "FINX",
        "Mortgage REITs": "REM",
        "Payments": "IPAY",
        "Regional Banks": "KRE",
    },
    "Consumer": {
        "Retail": "XRT",
        "E-Commerce": "IBUY",
        "Consumer Staples": "XLP",
        "Video Gaming": "ESPO",
        "Pet Care": "PAWZ",
        "Restaurants": "PBJ",
        "Automotive": "CARZ",
        "Luxury Goods": "LUXE",
    },
    "Energy & Materials": {
        "Materials": "XLB",
        "Lithium & Battery": "LIT",
        "Mining": "XME",
        "Nuclear Energy": "URA",
        "Oil & Gas": "XLE",
        "Renewable Energy": "ICLN",
        "Steel": "SLX",
    },
    "Industrials": {
        "Aerospace & Defense": "ITA",
        "Construction": "ITB",
        "Robotics & Automation": "ROBO",
        "Logistics": "FTXR",
        "Space": "UFO",
        "Airlines": "JETS",
        "Shipping": "BOAT",
    },
    "Real Estate & Infrastructure": {
        "Real Estate": "IYR",
        "Infrastructure": "PAVE",
        "Homebuilders": "XHB",
        "Commercial Real Estate": "INDS",
    },
    "Communications & Media": {
        "Media": "PBS",
        "Entertainment": "PEJ",
        "Social Media": "SOCL",
    },
    "Other": {
        "Utilities": "XLU",
        "Agriculture": "DBA",
        "Cannabis": "MSOS",
        "ESG": "ESGU",
    },
}

# Flat lookup: industry → (sector, etf)
_FLAT: dict[str, tuple[str, str]] = {
    industry: (sector, etf)
    for sector, industries in INDUSTRIES.items()
    for industry, etf in industries.items()
}


def _data_status(industries: dict[str, dict]) -> dict:
    """Summarize dataset completeness for a response.

    The multi-source fallback chain (Finnhub → yfinance → AlphaVantage) can
    exhaust every source for an individual ETF; that industry then carries an
    `error` field instead of a quote. The endpoint still returns HTTP 200, so
    callers need an explicit signal that the dataset is partial — otherwise a
    silently smaller result looks complete. See incident-2026-05-21.
    """
    total = len(industries)
    failed = sorted(k for k, v in industries.items() if "error" in v)
    return {
        "expected": total,
        "available": total - len(failed),
        "failed": len(failed),
        "partial": bool(failed),
        "failed_industries": failed,
    }


async def _fetch_quote_with_fallback(client: httpx.AsyncClient, etf: str) -> dict:
    """Fetch quote via the Finnhub → yfinance fallback chain.

    Delegates the whole chain to data_client.get_quote, which already does
    Finnhub (guarded against c=0 / None) → yfinance and reuses the shared
    client. This must not re-implement either source: a local Finnhub parse
    previously raised NoneType.__round__ TypeErrors, and calling _finnhub_quote
    here before get_quote queried Finnhub twice on every failure
    (incident-2026-05-21).
    """
    try:
        return await get_quote(etf, client=client)
    except Exception as exc:
        raise RuntimeError(f"All sources failed for {etf}: {exc}") from exc


async def get_industry_quotes() -> dict:
    """Fetch live quotes only — no returns computation.

    Cache key is bucketed by minute so Finnhub is called at most once per
    _QUOTE_CACHE_TTL_SECONDS across all concurrent requests (single-flight).
    """
    minute_bucket = floor(time.time() / _QUOTE_CACHE_TTL_SECONDS)
    cache_key = f"industry_quotes:{minute_bucket}"
    if cached := get_cache(cache_key):
        return cached

    async with _quotes_lock():
        # Re-check after lock — another coroutine may have already built it
        if cached := get_cache(cache_key):
            return cached

        async def fetch_one(industry: str, sector: str, etf: str):
            # Sleep before acquiring so waiting coroutines stagger their entry
            # times; sleeping inside the semaphore holds the slot while idle
            # and prevents other coroutines from starting (defeating the point).
            await asyncio.sleep(0.5)
            async with _etf_fetch_semaphore():
                try:
                    quote = await _fetch_quote_with_fallback(client, etf)
                    return industry, {"sector": sector, "etf": etf, **quote}
                except Exception as exc:
                    logger.error("industry_quotes: all sources failed for %s (%s): %s", industry, etf, exc)
                    return industry, {"sector": sector, "etf": etf, "error": str(exc)}

        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [
                fetch_one(industry, sector, etf)
                for industry, (sector, etf) in _FLAT.items()
            ]
            pairs = await asyncio.gather(*tasks)

        industries = dict(pairs)
        ranked = sorted(
            [{"industry": k, **v} for k, v in industries.items() if "change_pct" in v],
            key=lambda x: x["change_pct"],
            reverse=True,
        )
        by_sector: dict[str, list] = {}
        for row in ranked:
            by_sector.setdefault(row["sector"], []).append(row)

        result = {
            "date": str(date.today()),
            "quotes_as_of": _now_est_iso(),
            "total": len(industries),
            "data_status": _data_status(industries),
            "industries": industries,
            "rankings": ranked,
            "by_sector": by_sector,
            "leaders": ranked[:5],
            "laggards": ranked[-5:],
        }
        if ranked:
            # TTL longer than the bucket interval; key rotation enforces freshness
            set_cache(cache_key, result, ttl_hours=1)
        return result


async def compute_returns() -> dict:
    """Compute and persist multi-period returns from etf_store to industry_cache.

    Called by the scheduler via POST /admin/compute-returns. Reads from
    permanent ETF price history — zero Finnhub or AV API calls.
    """
    from firestore import db as _db

    # Build a minimal industries dict from FLAT (no live quotes needed)
    industries = {
        industry: {"sector": sector, "etf": etf}
        for industry, (sector, etf) in _FLAT.items()
    }
    _attach_stored_returns(industries)
    logger.info("compute_returns: completed for %d industries", len(industries))
    return {"status": "ok", "industries": len(industries)}


async def get_industry_data(enrich_av: bool = False, force: bool = False) -> dict:
    cache_key = f"industry_data:{date.today()}"
    if not force and (cached := get_cache(cache_key)):
        logger.info("industry_data: cache_hit key=%s", cache_key)
        return cached

    async with _industry_lock():
        # Re-check cache after acquiring lock (another coroutine may have built it)
        if not force and (cached := get_cache(cache_key)):
            logger.info("industry_data: cache_hit key=%s (post-lock)", cache_key)
            return cached

        logger.info("industry_data: cache_miss key=%s — fetching %d ETFs", cache_key, len(_FLAT))
        all_etfs = list({etf for _, etf in _FLAT.values()})
        t_quotes_start = time.monotonic()

        # Step 1: fetch all quotes (Finnhub → yfinance per symbol)
        async def fetch_one(industry: str, sector: str, etf: str):
            # Sleep before acquiring so waiting coroutines stagger their entry
            # times; sleeping inside the semaphore holds the slot while idle
            # and prevents other coroutines from starting (defeating the point).
            await asyncio.sleep(0.5)
            async with _etf_fetch_semaphore():
                try:
                    quote = await _fetch_quote_with_fallback(client, etf)
                    return industry, {"sector": sector, "etf": etf, **quote}
                except Exception as exc:
                    logger.error("industry: all_sources_failed industry=%s etf=%s error=%s", industry, etf, exc)
                    return industry, {"sector": sector, "etf": etf, "error": str(exc)}

        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [
                fetch_one(industry, sector, etf)
                for industry, (sector, etf) in _FLAT.items()
            ]
            pairs = await asyncio.gather(*tasks)

        industries = dict(pairs)
        failed_count = sum(1 for v in industries.values() if "error" in v)
        ok_count = len(industries) - failed_count
        t_quotes_ms = round((time.monotonic() - t_quotes_start) * 1000)
        logger.info(
            "industry_data: quotes_done ok=%d failed=%d total=%d ms=%d",
            ok_count, failed_count, len(industries), t_quotes_ms,
        )
        if failed_count > 0:
            failed_names = [k for k, v in industries.items() if "error" in v]
            logger.warning("industry_data: quote_failures industries=%s", failed_names)

        # Step 2: enrich with AV multi-period analytics (scheduler-only path)
        if enrich_av:
            valid_etfs = [
                etf for etf in all_etfs
                if not any(
                    v.get("etf") == etf and "error" in v
                    for v in industries.values()
                )
            ]
            av_quota_needed = (len(valid_etfs) + 4) // 5  # ceil div
            if await av_remaining_calls() >= av_quota_needed:
                logger.info(
                    "industry: enriching %d ETFs with AV analytics (%d calls needed)",
                    len(valid_etfs),
                    av_quota_needed,
                )
                try:
                    av_data = await av_analytics_batch(valid_etfs, range_="1month")
                    for industry, data in industries.items():
                        etf = data.get("etf")
                        if etf and etf in av_data and "error" not in data:
                            av = av_data[etf]
                            data["return_1m"] = av.get("cumulative_return")
                            data["mean_daily_return"] = av.get("mean")
                            data["stddev_daily"] = av.get("stddev")
                except Exception as exc:
                    logger.error("industry: AV analytics enrichment failed: %s", exc)
            else:
                av_remaining = await av_remaining_calls()
                logger.info(
                    "industry: skipping AV analytics — only %d calls remain (need %d)",
                    av_remaining,
                    av_quota_needed,
                )

        # Step 3: attach multi-period returns from permanent ETF store + persist to industry_cache
        t_returns_start = time.monotonic()
        _attach_stored_returns(industries)
        t_returns_ms = round((time.monotonic() - t_returns_start) * 1000)
        logger.info("industry_data: attach_stored_returns_done ms=%d", t_returns_ms)

        # Step 4: Enrich with Finnhub 52w high/low (replaces Polygon snapshot — always 403)
        try:
            metrics = await get_finnhub_metrics(all_etfs)
            for industry, data in industries.items():
                etf = data.get("etf")
                if etf and etf in metrics and "error" not in data:
                    m = metrics[etf]
                    data["week52_high"] = m.get("high_52week")
                    data["week52_low"] = m.get("low_52week")
                    logger.debug("industry_data metrics: %s = %s", etf, m)
        except Exception as exc:
            logger.warning("industry_data metrics enrichment failed: %s", exc)

        # Build rankings after all enrichment so rows include returns + 52W data
        ranked = sorted(
            [{"industry": k, **v} for k, v in industries.items() if "change_pct" in v],
            key=lambda x: x["change_pct"],
            reverse=True,
        )

        # Group by sector, maintaining rank order within each sector
        by_sector: dict[str, list] = {}
        for row in ranked:
            by_sector.setdefault(row["sector"], []).append(row)

        result = {
            "date": str(date.today()),
            "quotes_as_of": _now_est_iso(),
            "total": len(industries),
            "data_status": _data_status(industries),
            "industries": industries,
            "rankings": ranked,
            "by_sector": by_sector,
            "leaders": ranked[:5],
            "laggards": ranked[-5:],
        }

        if ranked:
            set_cache(cache_key, result, ttl_hours=24)
            logger.info("industry_data: cache_written key=%s industries=%d", cache_key, len(industries))
        else:
            logger.error("industry_data: no_valid_quotes — skipping cache write key=%s", cache_key)
        return result


def _attach_stored_returns(industries: dict) -> None:
    """Attach multi-period returns from etf_store and persist to industry_cache.

    For each ETF: compute returns from stored history, attach to the industry
    dict, and write to the industry_cache Firestore collection so
    industry_returns.py can read them without extra API calls.

    Also removes any orphaned industry_cache documents whose industry key is no
    longer present in the current INDUSTRIES dict (e.g. renamed or removed
    industries from prior runs).
    """
    from firestore import db as _db
    now_str = datetime.now(timezone.utc).isoformat()
    db = _db()
    batch = db.batch()
    ops = 0

    # Delete orphaned documents from previous industry sets
    current_keys = set(industries.keys())
    for ref in db.collection("industry_cache").list_documents():
        if ref.id not in current_keys:
            batch.delete(ref)
            ops += 1
            logger.info("industry: removing orphaned industry_cache doc '%s'", ref.id)
            if ops >= _FIRESTORE_BATCH_MAX_OPS:
                batch.commit()
                batch = db.batch()
                ops = 0

    # Load existing industry_cache docs as fallback for industries with no etf_store history
    cached_docs: dict[str, dict] = {}
    try:
        for doc in db.collection("industry_cache").stream():
            cached_docs[doc.id] = doc.to_dict()
    except Exception as exc:
        logger.warning("industry: could not pre-load industry_cache for fallback: %s", exc)

    # Deduplicate ETFs (multiple industries may share one ETF)
    etf_returns: dict[str, dict | None] = {}
    for data in industries.values():
        etf = data.get("etf")
        if etf and etf not in etf_returns:
            etf_returns[etf] = etf_store.compute_returns(etf)

    for industry, data in industries.items():
        etf = data.get("etf")
        returns = etf_returns.get(etf) if etf else None
        if returns:
            data["returns"] = {k: v for k, v in returns.items()
                               if not k.endswith("_high") and not k.endswith("_low")}
            data["52w_high"] = returns.get("52w_high")
            data["52w_low"] = returns.get("52w_low")
        elif industry in cached_docs:
            # etf_store has no history yet — use what's already in industry_cache
            cached = cached_docs[industry]
            if cached.get("returns"):
                data["returns"] = cached["returns"]
            if cached.get("52w_high") is not None:
                data["52w_high"] = cached["52w_high"]
            if cached.get("52w_low") is not None:
                data["52w_low"] = cached["52w_low"]

        # Persist to industry_cache for industry_returns.py
        doc_ref = db.collection("industry_cache").document(industry)
        batch.set(doc_ref, {
            "industry": industry,
            "sector": data.get("sector"),
            "etf": etf,
            "returns": data.get("returns", {}),
            "52w_high": data.get("52w_high"),
            "52w_low": data.get("52w_low"),
            "updated": now_str,
        })
        ops += 1
        if ops >= _FIRESTORE_BATCH_MAX_OPS:
            batch.commit()
            batch = db.batch()
            ops = 0

    if ops:
        batch.commit()
    logger.info(
        "industry_cache: write_complete industries=%d timestamp=%s",
        len(industries), now_str,
    )


async def seed_etf_history(force: bool = False, symbols: list[str] | None = None) -> dict[str, int]:
    """Seed or delta-update permanent ETF history for all tracked industries.

    Call once at startup or via a scheduled endpoint. Uses yfinance batch
    download (one HTTP request for all tickers) to avoid per-ticker rate limits.
    Full history on first run; 3-month window on subsequent delta runs.

    Args:
        force: If True, deletes etf_history/{SYMBOL} docs before reseeding.
            Use when stored history is corrupted (e.g. wrong-signed returns
            from an upstream bug). Existing data is unrecoverable after this.
        symbols: If set, restrict the operation to just these ETFs. Useful
            for surgical reseeds (only the offenders from /admin/audit-etf-history)
            instead of nuking all 54.

    Returns:
        Dict mapping ETF symbol → rows stored/appended.
    """
    import yfinance as yf

    unique_etfs = list({etf for _, etf in _FLAT.values()})
    if symbols:
        wanted = {s.upper() for s in symbols}
        unique_etfs = [e for e in unique_etfs if e.upper() in wanted]
        logger.info("seed_etf_history: restricted to %d/%d ETFs", len(unique_etfs), len(wanted))

    results: dict[str, int] = {}

    from firestore import db as _db
    _firestore = _db()
    refs = [_firestore.collection(etf_store._COLLECTION).document(e.upper()) for e in unique_etfs]

    if force:
        # Destructive: drop existing docs so the seed path runs (full history)
        # instead of the delta-append path. Required when stored prices are
        # corrupted and can no longer be trusted as the base for an append.
        logger.warning("seed_etf_history: force=True — deleting %d existing docs", len(refs))

        def _delete_all_force() -> None:
            """Batched, threadpool-friendly destructive cleanup.

            Streams + deletes per-year sub-docs in batches of up to 450 ops
            (Firestore caps at 500), then deletes the parent docs in a
            single batch. Runs synchronously inside run_in_executor so the
            async event loop isn't blocked across 54 ETFs.
            """
            batch = _firestore.batch()
            ops = 0
            for ref in refs:
                # Delete the per-year subcollection first
                for yr_snap in ref.collection("years").stream():
                    batch.delete(yr_snap.reference)
                    ops += 1
                    if ops >= _FIRESTORE_BATCH_MAX_OPS:
                        batch.commit()
                        batch = _firestore.batch()
                        ops = 0
                # Then the parent doc
                batch.delete(ref)
                ops += 1
                if ops >= _FIRESTORE_BATCH_MAX_OPS:
                    batch.commit()
                    batch = _firestore.batch()
                    ops = 0
            if ops:
                batch.commit()

        await asyncio.get_running_loop().run_in_executor(None, _delete_all_force)

    snaps = _firestore.get_all(refs)
    existing_symbols = {snap.id for snap in snaps if snap.exists}
    new_etfs = [e for e in unique_etfs if e.upper() not in existing_symbols]
    delta_etfs = [e for e in unique_etfs if e.upper() in existing_symbols]

    # Batch download — one request per group instead of 54 individual calls
    batches: list[tuple[list[str], str, str]] = []
    if new_etfs:
        batches.append((new_etfs, "max", "yfinance_seed"))
    if delta_etfs:
        batches.append((delta_etfs, "3mo", "yfinance_delta"))

    for etfs, period, source in batches:
        # yfinance has aggressive rate limiting on batch downloads.
        # Download individual ETFs or very small batches (2-3) with delays between.
        logger.info("seed_etf_history: downloading %d ETFs individually (period=%s) to avoid rate limits",
                   len(etfs), period)

        for etf_idx, etf in enumerate(etfs):
            # Rate-limit ourselves: wait 0.5s between downloads
            if etf_idx > 0:
                await asyncio.sleep(0.5)

            logger.debug("seed_etf_history: fetching %s (%d/%d, period=%s)",
                        etf, etf_idx+1, len(etfs), period)

            # Retry up to 3 times with exponential backoff
            raw = None
            for attempt in range(3):
                try:
                    raw = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda e=etf, p=period: yf.download(
                            e, period=p, auto_adjust=True, progress=False, threads=False
                        ),
                    )
                    break  # Success, exit retry loop
                except Exception as exc:
                    if attempt < 2:
                        wait_seconds = 2 ** attempt  # 1s, 2s
                        logger.warning("seed_etf_history: %s attempt %d failed, retrying in %ds: %s",
                                     etf, attempt+1, wait_seconds, exc)
                        await asyncio.sleep(wait_seconds)
                    else:
                        logger.error("seed_etf_history: %s failed after 3 attempts: %s",
                                   etf, exc)
                        raw = None

            if raw is None or raw.empty:
                results[etf] = 0
                continue

            # yfinance returns a MultiIndex DataFrame even for single-ticker
            # downloads (cols are tuples like ('Close', 'HACK')). Flatten
            # before slicing or we'll get DataFrame-not-Series back and the
            # pd.DataFrame() constructor raises "all scalar values" errors.
            try:
                if isinstance(raw, pd.DataFrame) and isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [c[0] for c in raw.columns]

                if isinstance(raw, pd.DataFrame):
                    close_series = raw["Close"]
                    volume_series = raw["Volume"]
                else:
                    close_series = raw
                    volume_series = pd.Series([0] * len(raw), index=raw.index)

                hist = pd.DataFrame({
                    "adjusted_close": close_series,
                    "volume": volume_series
                }).dropna()

                if source == "yfinance_seed":
                    rows = etf_store.store_history(etf, hist, source=source)
                else:
                    rows = etf_store.append_daily(etf, hist, source=source)
                results[etf] = rows
            except Exception as exc:
                logger.error("seed_etf_history: store failed for %s: %s", etf, exc)
                results[etf] = 0

    logger.info("seed_etf_history complete: %d ETFs, %d total rows", len(results), sum(results.values()))
    return results


async def audit_etf_history(drift_threshold_pct: float = 1.0) -> dict:
    """Compare each stored ETF latest close against a fresh yfinance pull.

    Surfaces silent corruption of the etf_history collection (the root cause
    behind the 2026-05-15 backtest finding where HACK 1m cached at -9.27%
    while yfinance reported +13.62%).

    Args:
        drift_threshold_pct: Symbols whose stored vs yfinance latest close
            differ by more than this percentage are flagged.

    Returns:
        {
          "checked": int,                # ETFs with stored history
          "missing_yfinance": [str],     # could not get a yfinance reference
          "drifting": [{symbol, stored_close, yfinance_close, drift_pct, stored_date, yfinance_date}],
        }
    """
    import yfinance as yf

    unique_etfs = list({etf for _, etf in _FLAT.values()})
    drifting: list[dict] = []
    missing: list[str] = []
    checked = 0

    loop = asyncio.get_running_loop()

    for etf in unique_etfs:
        # load_history hits Firestore synchronously — push to a thread so the
        # event loop stays free across the 54-symbol audit pass.
        stored = await loop.run_in_executor(None, etf_store.load_history, etf)
        if stored is None or stored.empty:
            missing.append(etf)
            continue
        checked += 1
        stored_close = float(stored["adjusted_close"].iloc[0])
        stored_date = stored.index[0].strftime("%Y-%m-%d")

        try:
            raw = await loop.run_in_executor(
                None,
                lambda e=etf: yf.download(
                    e, period="5d", auto_adjust=True, progress=False, threads=False
                ),
            )
        except Exception as exc:
            logger.warning("audit_etf_history: yfinance failed for %s: %s", etf, exc)
            missing.append(etf)
            continue

        if raw is None or raw.empty:
            missing.append(etf)
            continue

        # yfinance.download returns a MultiIndex DataFrame even for a single
        # ticker; raw["Close"] then yields a DataFrame, not a Series, and
        # float(closes.iloc[-1]) raises further down. Flatten before slicing.
        if isinstance(raw, pd.DataFrame) and isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] for c in raw.columns]

        close_col = raw["Close"] if isinstance(raw, pd.DataFrame) else raw
        closes = close_col.dropna()
        if closes.empty:
            missing.append(etf)
            continue
        yf_close = float(closes.iloc[-1])
        yf_date = closes.index[-1].strftime("%Y-%m-%d")
        if yf_close == 0:
            missing.append(etf)
            continue

        drift_pct = abs(stored_close - yf_close) / yf_close * 100
        if drift_pct > drift_threshold_pct:
            drifting.append({
                "symbol": etf,
                "stored_close": round(stored_close, 2),
                "yfinance_close": round(yf_close, 2),
                "drift_pct": round(drift_pct, 2),
                "stored_date": stored_date,
                "yfinance_date": yf_date,
            })

        # Pace yfinance to dodge rate limits — same 0.5s used in seed loop
        await asyncio.sleep(0.5)

    drifting.sort(key=lambda d: -d["drift_pct"])
    logger.info(
        "audit_etf_history: checked=%d drifting=%d missing=%d threshold=%.2f%%",
        checked, len(drifting), len(missing), drift_threshold_pct,
    )
    return {
        "checked": checked,
        "drift_threshold_pct": drift_threshold_pct,
        "missing_yfinance": missing,
        "drifting": drifting,
        "drifting_symbols": [d["symbol"] for d in drifting],
    }
