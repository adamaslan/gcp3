"""Feature #18 — Sector-Relative Returns.

Computes per-ticker returns relative to sector ETF and SPY across all 6 timeframes.
Also derives sector rank, leader/laggard flags, and momentum_shift.
Data source: yfinance OHLCV (bars already fetched for technicals — zero extra cost).
"""
import logging
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)

# GICS sector → ETF mapping
SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "ConsumerDiscretionary": "XLY",
    "ConsumerStaples": "XLP",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Utilities": "XLU",
    "RealEstate": "XLRE",
    "CommunicationServices": "XLC",
}

TIMEFRAME_WINDOWS: dict[str, int] = {
    "1D": 1,
    "5D": 5,
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
}


@dataclass
class RelativeReturns:
    ticker: str
    sector: str
    sector_etf: str
    per_tf_absolute: dict[str, float] = field(default_factory=dict)
    per_tf_vs_sector: dict[str, float] = field(default_factory=dict)
    per_tf_vs_market: dict[str, float] = field(default_factory=dict)
    per_tf_sector_rank: dict[str, int] = field(default_factory=dict)
    per_tf_sector_rank_pct: dict[str, float] = field(default_factory=dict)
    is_sector_leader: bool = False
    is_sector_laggard: bool = False
    momentum_shift: Literal["improving_vs_sector", "weakening_vs_sector", "stable"] = "stable"


def _period_return(closes: pd.Series, window: int) -> float:
    if len(closes) < window + 1:
        return 0.0
    start = float(closes.iloc[-(window + 1)])
    end = float(closes.iloc[-1])
    return (end - start) / start if start > 0 else 0.0


def compute_relative_returns(
    ticker: str,
    sector: str,
    ticker_closes: pd.Series,
    sector_etf_closes: pd.Series,
    spy_closes: pd.Series,
    sector_peers_closes: dict[str, pd.Series] | None = None,
) -> RelativeReturns:
    """Compute sector-relative and market-relative returns.

    Args:
        ticker: Target ticker symbol.
        sector: GICS sector name.
        ticker_closes: Daily closing prices for the ticker (oldest first).
        sector_etf_closes: Closing prices for the sector ETF.
        spy_closes: SPY closing prices.
        sector_peers_closes: Optional dict of {peer: closes} for ranking.

    Returns:
        RelativeReturns with absolute, vs-sector, and vs-market data.
    """
    sector_etf = SECTOR_ETFS.get(sector, "SPY")
    result = RelativeReturns(ticker=ticker, sector=sector, sector_etf=sector_etf)

    for tf, window in TIMEFRAME_WINDOWS.items():
        abs_ret = _period_return(ticker_closes, window)
        sector_ret = _period_return(sector_etf_closes, window)
        market_ret = _period_return(spy_closes, window)
        result.per_tf_absolute[tf] = round(abs_ret, 4)
        result.per_tf_vs_sector[tf] = round(abs_ret - sector_ret, 4)
        result.per_tf_vs_market[tf] = round(abs_ret - market_ret, 4)

    # Rank within sector peers on 1M basis (if peers provided)
    if sector_peers_closes:
        peer_returns_1m = {
            p: _period_return(cls, TIMEFRAME_WINDOWS["1M"])
            for p, cls in sector_peers_closes.items()
        }
        peer_returns_1m[ticker] = result.per_tf_absolute.get("1M", 0.0)
        sorted_peers = sorted(peer_returns_1m.items(), key=lambda x: x[1], reverse=True)
        rank_map = {sym: i + 1 for i, (sym, _) in enumerate(sorted_peers)}
        total = len(sorted_peers)
        rank_1m = rank_map.get(ticker, total // 2)
        result.per_tf_sector_rank["1M"] = rank_1m
        result.per_tf_sector_rank_pct["1M"] = round(1 - (rank_1m - 1) / max(total - 1, 1), 3)
        result.is_sector_leader = rank_1m <= max(1, total // 10)
        result.is_sector_laggard = rank_1m >= total - max(0, total // 10)

    # Momentum shift: compare 1M vs-sector return trend
    vs_sector_1m = result.per_tf_vs_sector.get("1M", 0.0)
    vs_sector_5d = result.per_tf_vs_sector.get("5D", 0.0)
    if vs_sector_5d > vs_sector_1m + 0.005:
        result.momentum_shift = "improving_vs_sector"
    elif vs_sector_5d < vs_sector_1m - 0.005:
        result.momentum_shift = "weakening_vs_sector"
    else:
        result.momentum_shift = "stable"

    return result


def format_relative_for_prompt(r: RelativeReturns) -> str:
    rank_str = f"rank {r.per_tf_sector_rank.get('1M', '?')}" if r.per_tf_sector_rank else ""
    return (
        f"<relative>\n"
        f"  vs_sector_1d={r.per_tf_vs_sector.get('1D', 0):.1%} ({rank_str}) "
        f"vs_market_1d={r.per_tf_vs_market.get('1D', 0):.1%}\n"
        f"  vs_sector_1m={r.per_tf_vs_sector.get('1M', 0):.1%} "
        f"leader={str(r.is_sector_leader).lower()} laggard={str(r.is_sector_laggard).lower()}\n"
        f"  momentum={r.momentum_shift}\n"
        f"</relative>"
    )
