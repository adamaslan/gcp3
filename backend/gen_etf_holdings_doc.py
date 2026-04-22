"""Generate holdings data for ETFs using Yahoo Finance JSON API (async).

Pure CLI with no browser dependency. Uses httpx for async concurrent fetches.
Fetches top N holdings per ETF from Yahoo Finance's quoteSummary API.

Usage as module:
    from backend.gen_etf_holdings_doc import fetch_top_holdings, fetch_all_holdings, Holding

    async with httpx.AsyncClient() as client:
        holdings = await fetch_top_holdings(client, "IGV", limit=4)
        all_holdings = await fetch_all_holdings(["IGV", "SOXX"], limit=4)
"""
import asyncio
import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_YF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
_YF_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=topHoldings"


@dataclass(frozen=True)
class Holding:
    etf: str
    symbol: str
    name: str
    weight: float  # e.g. 0.0823 = 8.23%


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


async def fetch_top_holdings(
    client: httpx.AsyncClient,
    ticker: str,
    limit: int = 4,
) -> list[Holding]:
    """Fetch top N holdings for a given ETF ticker.

    Args:
        client: httpx.AsyncClient instance for making requests.
        ticker: ETF ticker symbol (e.g. "IGV").
        limit: Number of top holdings to fetch (default 4).

    Returns:
        List of Holding dataclasses. Empty list on fetch failure.
    """
    url = _YF_URL.format(symbol=ticker)
    try:
        resp = await client.get(url, headers=_YF_HEADERS, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        result = data.get("quoteSummary", {}).get("result")
        if not result:
            logger.warning("No quoteSummary result for %s", ticker)
            return []

        raw_holdings = result[0].get("topHoldings", {}).get("holdings", [])
        holdings: list[Holding] = []

        for h in raw_holdings[:limit]:
            weight = h.get("holdingPercent", {}).get("raw")
            if weight is None:
                weight = 0.0
            holdings.append(
                Holding(
                    etf=ticker,
                    symbol=h.get("symbol", ""),
                    name=h.get("holdingName", ""),
                    weight=float(weight),
                )
            )

        return holdings

    except httpx.HTTPError as e:
        logger.warning("HTTP error fetching %s: %s", ticker, e)
        return []
    except Exception as e:
        logger.warning("Error fetching %s: %s", ticker, e)
        return []


async def fetch_all_holdings(
    tickers: list[str],
    limit: int = 4,
    concurrency: int = 10,
) -> dict[str, list[Holding]]:
    """Fetch holdings for multiple tickers with concurrency control.

    Args:
        tickers: List of ETF ticker symbols.
        limit: Number of top holdings per ETF (default 4).
        concurrency: Max parallel requests (default 10, cap 20).

    Returns:
        Dict keyed by ticker → list of Holding dataclasses.
        Failed tickers yield empty lists and are logged.
    """
    concurrency = min(max(concurrency, 1), 20)
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_with_sem(client: httpx.AsyncClient, ticker: str) -> tuple[str, list[Holding]]:
        async with semaphore:
            holdings = await fetch_top_holdings(client, ticker, limit=limit)
            return ticker, holdings

    async with httpx.AsyncClient() as client:
        tasks = [fetch_with_sem(client, ticker) for ticker in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    return {ticker: holdings for ticker, holdings in results}


def holdings_to_csv_row(holding: Holding) -> dict:
    """Convert a Holding to a CSV row dict.

    Returns dict with keys: etf, symbol, name, weight.
    """
    return {
        "etf": holding.etf,
        "symbol": holding.symbol,
        "name": holding.name,
        "weight": f"{holding.weight:.4f}" if holding.weight is not None else "",
    }


async def main_async() -> None:
    """Fetch all industry ETF holdings and write to CSV."""
    all_tickers = [etf for industries in INDUSTRIES.values() for etf in industries.values()]
    print(f"Fetching holdings for {len(all_tickers)} ETFs...")

    holdings_by_ticker = await fetch_all_holdings(all_tickers, limit=4, concurrency=10)

    csv_rows: list[dict] = []
    for ticker in all_tickers:
        holdings = holdings_by_ticker.get(ticker, [])
        for holding in holdings:
            csv_rows.append(holdings_to_csv_row(holding))

    output = Path(__file__).parent.parent / "docs" / "etf-holdings.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["etf", "symbol", "name", "weight"])
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"✓ Written {len(csv_rows)} holdings to {output}")


def main() -> None:
    """Sync wrapper for CLI invocation."""
    asyncio.run(main_async())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
