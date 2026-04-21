"""Feature #15 — Rolling Correlation Matrix.

Computes per-ticker correlation summaries:
  - avg_sector_corr, avg_market_corr (SPY)
  - idiosyncratic_score (1 - market_corr)
  - regime flag: decoupling / normal / tight

For full pairwise matrix: delegate to BigQuery SQL (too large for in-process).
This module handles per-ticker summary computation from daily-return DataFrames.
"""
import logging
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CorrelationSummary:
    ticker: str
    window_days: int
    avg_sector_corr: float
    avg_market_corr: float
    most_correlated: list[tuple[str, float]] = field(default_factory=list)
    least_correlated: list[tuple[str, float]] = field(default_factory=list)
    corr_zscore_vs_history: float = 0.0
    idiosyncratic_score: float = 0.0
    regime_flag: str = "normal"


def compute_correlation_summary(
    ticker: str,
    ticker_returns: pd.Series,
    spy_returns: pd.Series,
    sector_peers: dict[str, pd.Series],
    window_days: int = 30,
) -> CorrelationSummary | None:
    """Compute correlation summary for a single ticker.

    Args:
        ticker: The target ticker symbol.
        ticker_returns: Daily return series for the ticker (oldest first).
        spy_returns: Daily return series for SPY (same index).
        sector_peers: Dict of {peer_ticker: return_series} for same sector.
        window_days: Rolling window in days (default 30).

    Returns:
        CorrelationSummary or None if insufficient data.
    """
    if len(ticker_returns) < window_days:
        logger.warning("correlation: insufficient data for %s", ticker)
        return None

    t = ticker_returns.tail(window_days)
    spy = spy_returns.tail(window_days).reindex(t.index)

    market_corr = float(t.corr(spy)) if spy.notna().sum() > 5 else 0.0
    idiosyncratic = 1.0 - abs(market_corr)

    peer_corrs: list[tuple[str, float]] = []
    for peer, peer_rets in sector_peers.items():
        if peer == ticker:
            continue
        p = peer_rets.tail(window_days).reindex(t.index)
        c = float(t.corr(p)) if p.notna().sum() > 5 else float("nan")
        if not np.isnan(c):
            peer_corrs.append((peer, round(c, 3)))

    avg_sector = float(np.mean([c for _, c in peer_corrs])) if peer_corrs else 0.0
    sorted_peers = sorted(peer_corrs, key=lambda x: x[1], reverse=True)

    # Regime flag: decoupling if market corr dropped > 2σ vs its own 90d history
    regime_flag = "normal"
    if len(ticker_returns) >= 90:
        roll_corr_90d = ticker_returns.rolling(window=30).corr(spy_returns).dropna()
        if len(roll_corr_90d) >= 5:
            hist_mean = float(np.mean(roll_corr_90d[:-1]))
            hist_std = float(np.std(roll_corr_90d[:-1]))
            if hist_std > 0:
                zscore = (market_corr - hist_mean) / hist_std
                if zscore < -2.0:
                    regime_flag = "decoupling"
                elif zscore > 2.0:
                    regime_flag = "tight"

    return CorrelationSummary(
        ticker=ticker,
        window_days=window_days,
        avg_sector_corr=round(avg_sector, 3),
        avg_market_corr=round(market_corr, 3),
        most_correlated=sorted_peers[:5],
        least_correlated=sorted_peers[-5:] if len(sorted_peers) >= 5 else [],
        corr_zscore_vs_history=0.0,
        idiosyncratic_score=round(idiosyncratic, 3),
        regime_flag=regime_flag,
    )


def format_correlation_for_prompt(c: CorrelationSummary) -> str:
    top = ", ".join(f"{t}:{v:.2f}" for t, v in c.most_correlated[:3])
    return (
        f"<correlation>"
        f"sector_avg={c.avg_sector_corr:.2f} market(SPY)={c.avg_market_corr:.2f} "
        f"idiosync={c.idiosyncratic_score:.2f}\n"
        f"  top_corr=[{top}]\n"
        f"  regime={c.regime_flag}"
        f"</correlation>"
    )
