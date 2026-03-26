"""Industry Tracker: 50-industry ETF performance.

Data resolution chain per ETF:
  1. Finnhub — real-time intraday quote (primary)
  2. yfinance — free fallback when Finnhub fails (no quota)
  3. Alpha Vantage ANALYTICS_FIXED_WINDOW — batched (5 symbols/call),
     enriches valid quotes with multi-period returns (1m, 3m, 1y)
     when AV quota allows; pure bonus data, never blocks quotes

Permanent storage (etf_store):
  - On first run, seeds full price history for all 50 ETFs via yfinance
  - Daily refresh appends only new trading days (delta fetch)
  - Multi-period returns calculated from stored history (zero API calls)
  - Populates industry_cache collection consumed by industry_returns.py
"""
import asyncio
import logging
from datetime import date

import httpx

from data_client import av_analytics_batch, av_remaining_calls, finnhub_get, get_cache, get_quote, set_cache
import etf_store

logger = logging.getLogger(__name__)

# 50 industries → ETF, organized by sector group
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
        "REITs": "VNQ",
        "Payments": "IPAY",
        "Regional Banks": "KRE",
    },
    "Consumer": {
        "Retail": "XRT",
        "E-Commerce": "IBUY",
        "Consumer Staples": "XLP",
        "Consumer Discretionary": "XLY",
        "Restaurants": "BITE",
        "Apparel": "PEJ",
        "Automotive": "CARZ",
        "Luxury Goods": "LUXE",
    },
    "Energy & Materials": {
        "Oil & Gas": "XLE",
        "Renewable Energy": "ICLN",
        "Mining": "XME",
        "Steel": "SLX",
        "Chemicals": "XLB",
    },
    "Industrials": {
        "Aerospace & Defense": "ITA",
        "Transportation": "XTN",
        "Construction": "ITB",
        "Logistics": "FTXR",
        "Industrials": "XLI",
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


async def _fetch_quote_with_fallback(client: httpx.AsyncClient, etf: str) -> dict:
    """Fetch quote via Finnhub, falling back to yfinance on failure."""
    try:
        d = await finnhub_get(client, "/quote", {"symbol": etf})
        return {
            "price": round(d["c"], 2),
            "change": round(d["d"], 2),
            "change_pct": round(d["dp"], 2),
            "source": "finnhub",
        }
    except Exception as finnhub_exc:
        logger.warning("industry: Finnhub failed for %s (%s) — trying yfinance", etf, finnhub_exc)
        try:
            return await get_quote(etf)
        except Exception as yf_exc:
            raise RuntimeError(
                f"All sources failed for {etf}: finnhub={finnhub_exc} yfinance={yf_exc}"
            ) from yf_exc


async def get_industry_data() -> dict:
    cache_key = f"industry50:{date.today()}"
    if cached := get_cache(cache_key):
        return cached

    all_etfs = list({etf for _, etf in _FLAT.values()})

    # Step 1: fetch all quotes (Finnhub → yfinance per symbol)
    async def fetch_one(industry: str, sector: str, etf: str):
        try:
            quote = await _fetch_quote_with_fallback(client, etf)
            return industry, {"sector": sector, "etf": etf, **quote}
        except Exception as exc:
            logger.error("industry: all sources failed for %s (%s): %s", industry, etf, exc)
            return industry, {"sector": sector, "etf": etf, "error": str(exc)}

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [
            fetch_one(industry, sector, etf)
            for industry, (sector, etf) in _FLAT.items()
        ]
        pairs = await asyncio.gather(*tasks)

    industries = dict(pairs)

    # Step 2: enrich with AV multi-period analytics if quota allows
    # 50 ETFs → 10 AV calls (5 symbols/call) — only runs if quota available
    valid_etfs = [
        etf for etf in all_etfs
        if not any(
            v.get("etf") == etf and "error" in v
            for v in industries.values()
        )
    ]
    av_quota_needed = (len(valid_etfs) + 4) // 5  # ceil div
    if av_remaining_calls() >= av_quota_needed:
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
        logger.info(
            "industry: skipping AV analytics — only %d calls remain (need %d)",
            av_remaining_calls(),
            av_quota_needed,
        )

    # Rankings (only entries with valid quote data)
    ranked = sorted(
        [{"industry": k, **v} for k, v in industries.items() if "change_pct" in v],
        key=lambda x: x["change_pct"],
        reverse=True,
    )

    # Group by sector, maintaining rank order within each sector
    by_sector: dict[str, list] = {}
    for row in ranked:
        by_sector.setdefault(row["sector"], []).append(row)

    # Step 3: attach multi-period returns from permanent ETF store + persist to industry_cache
    _attach_stored_returns(industries)

    result = {
        "date": str(date.today()),
        "total": len(industries),
        "industries": industries,
        "rankings": ranked,
        "by_sector": by_sector,
        "leaders": ranked[:5],
        "laggards": ranked[-5:],
    }

    if ranked:
        set_cache(cache_key, result, ttl_hours=24)
    return result


def _attach_stored_returns(industries: dict) -> None:
    """Attach multi-period returns from etf_store and persist to industry_cache.

    For each ETF: compute returns from stored history, attach to the industry
    dict, and write to the industry_cache Firestore collection so
    industry_returns.py can read them without extra API calls.
    """
    from firestore import db as _db
    now_str = datetime.utcnow().isoformat()
    db = _db()
    batch = db.batch()
    ops = 0

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
        if ops >= 450:
            batch.commit()
            batch = db.batch()
            ops = 0

    if ops:
        batch.commit()
    logger.info("industry: persisted %d industries to industry_cache", len(industries))


async def seed_etf_history() -> dict[str, int]:
    """Seed or delta-update permanent ETF history for all 50 industries.

    Call once at startup or via a scheduled endpoint. Uses yfinance for
    full history on first run; appends only new days on subsequent runs.

    Returns:
        Dict mapping ETF symbol → rows stored/appended.
    """
    import yfinance as yf

    unique_etfs = list({etf for _, etf in _FLAT.values()})
    results: dict[str, int] = {}

    for etf in unique_etfs:
        meta = etf_store.get_metadata(etf)
        try:
            ticker = yf.Ticker(etf)
            period = "max" if meta is None else "3mo"
            hist = ticker.history(period=period)
            if hist.empty:
                logger.warning("seed_etf_history: no data for %s", etf)
                continue
            hist = hist.rename(columns={"Close": "adjusted_close", "Volume": "volume"})
            if meta is None:
                rows = etf_store.store_history(etf, hist, source="yfinance_seed")
            else:
                rows = etf_store.append_daily(etf, hist, source="yfinance_delta")
            results[etf] = rows
        except Exception as exc:
            logger.error("seed_etf_history: failed for %s: %s", etf, exc)
            results[etf] = 0

    logger.info("seed_etf_history complete: %d ETFs, %d total rows", len(results), sum(results.values()))
    return results


# Deferred import to avoid circular at module level
from datetime import datetime  # noqa: E402 (used in _attach_stored_returns)
