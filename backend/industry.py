"""Industry Tracker: 50-industry ETF performance.

Data resolution chain per ETF:
  1. Finnhub — real-time intraday quote (primary)
  2. yfinance — free fallback when Finnhub fails (no quota)
  3. Alpha Vantage ANALYTICS_FIXED_WINDOW — batched (5 symbols/call),
     enriches valid quotes with multi-period returns (1m, 3m, 1y)
     when AV quota allows; pure bonus data, never blocks quotes
"""
import asyncio
import logging
from datetime import date

import httpx

from data_client import av_analytics_batch, av_remaining_calls, finnhub_get, get_cache, get_quote, set_cache

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
