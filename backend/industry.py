"""Industry Tracker: 50-industry ETF performance via Finnhub."""
import asyncio
import os
from datetime import date

import httpx

from firestore import get_cache, set_cache

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


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    r = await client.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": symbol, "token": os.environ["FINNHUB_API_KEY"]},
    )
    r.raise_for_status()
    d = r.json()
    return {
        "price": round(d["c"], 2),
        "change": round(d["d"], 2),
        "change_pct": round(d["dp"], 2),
    }


async def get_industry_data() -> dict:
    cache_key = f"industry50:{date.today()}"
    if cached := get_cache(cache_key):
        return cached

    async def fetch_one(industry: str, sector: str, etf: str):
        try:
            quote = await _fetch_quote(client, etf)
            return industry, {"sector": sector, "etf": etf, **quote}
        except Exception as exc:
            return industry, {"sector": sector, "etf": etf, "error": str(exc)}

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [
            fetch_one(industry, sector, etf)
            for industry, (sector, etf) in _FLAT.items()
        ]
        pairs = await asyncio.gather(*tasks)

    industries = dict(pairs)

    # Rankings (only entries with valid data)
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

    set_cache(cache_key, result, ttl_hours=24)
    return result
