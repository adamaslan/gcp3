"""Momentum-based swing trade predictions using technical indicators.

Predicts 10 buy and 10 sell candidates for 2-week to 1-month swing trades
based on previous momentum and technical indicators.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import yfinance as yf
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator, ROCIndicator
from ta.trend import MACD, SMAIndicator, EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange

logger = logging.getLogger(__name__)
_YF_SEMAPHORE = asyncio.Semaphore(4)

# High-liquidity stocks for swing trading
SWING_WATCHLIST: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "JPM", "V",
    "JNJ", "WMT", "PG", "MA", "UNH", "HD", "DIS", "BAC", "XOM", "CVX",
    "KO", "PEP", "COST", "ABT", "MRK", "AVGO", "LLY", "ORCL", "CSCO", "ACN",
    "TMO", "MCD", "ABBV", "DHR", "NEE", "TXN", "PM", "UPS", "BMY", "QCOM",
    "HON", "LOW", "INTC", "AMD", "SBUX", "BA", "CAT", "GE", "IBM", "GS",
    "AIG", "C", "AXP", "MS", "BLK", "SCHW", "SPGI", "MMC", "USB", "PNC",
]


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate technical indicators for momentum analysis."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # RSI (14-period)
    df["rsi"] = RSIIndicator(close, window=14).rsi()

    # Stochastic (14, 3, 3)
    stoch = StochasticOscillator(high, low, close, window=14, smooth3=3)
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # MACD (12, 26, 9)
    macd = MACD(close)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    # Moving averages
    df["sma_20"] = SMAIndicator(close, window=20).sma_indicator()
    df["sma_50"] = SMAIndicator(close, window=50).sma_indicator()
    df["sma_200"] = SMAIndicator(close, window=200).sma_indicator()
    df["ema_9"] = EMAIndicator(close, window=9).ema_indicator()

    # Rate of Change (12-period)
    df["roc"] = ROCIndicator(close, window=12).roc()

    # ADX (14-period) - trend strength
    adx = ADXIndicator(high, low, close, window=14)
    df["adx"] = adx.adx()

    # Bollinger Bands
    bb = BollingerBands(close, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()

    # ATR (14-period)
    df["atr"] = AverageTrueRange(high, low, close, window=14).average_true_range()

    # Price momentum (2-week = 10 trading days)
    df["momentum_10d"] = close.pct_change(10) * 100

    # Price momentum (1-month = 21 trading days)
    df["momentum_21d"] = close.pct_change(21) * 100

    # Volume momentum
    df["volume_ratio"] = volume / volume.rolling(20).mean()

    return df


def _score_buy_signal(row: pd.Series) -> float:
    """Score a stock for buy signal (higher = stronger buy)."""
    score = 0.0

    # RSI: oversold to bullish reversal (40-60 is ideal accumulation zone)
    if 40 <= row.get("rsi", 50) <= 60:
        score += 2.0
    elif row.get("rsi", 50) < 30:
        score += 1.5  # oversold - potential bounce
    elif row.get("rsi", 50) > 70:
        score -= 1.0  # overbought - caution

    # Stochastic: bullish crossover
    if row.get("stoch_k", 50) > row.get("stoch_d", 50) and row.get("stoch_k", 50) < 30:
        score += 2.0

    # MACD: bullish momentum
    if row.get("macd", 0) > row.get("macd_signal", 0) and row.get("macd_hist", 0) > 0:
        score += 2.0

    # Price above moving averages (uptrend)
    if row.get("Close", 0) > row.get("sma_20", 0) > row.get("sma_50", 0):
        score += 2.0

    # Strong momentum (positive 10d and 21d)
    momentum_10d = row.get("momentum_10d", 0)
    momentum_21d = row.get("momentum_21d", 0)
    if momentum_10d > 0 and momentum_21d > 0:
        score += min(momentum_10d + momentum_21d, 4.0)  # cap at 4

    # ADX: strong trend (but not too strong = exhaustion)
    adx = row.get("adx", 0)
    if 25 <= adx <= 40:
        score += 1.5  # strong trend
    elif adx > 50:
        score -= 1.0  # possible exhaustion

    # Price near lower Bollinger Band (potential support)
    if row.get("Close", 0) <= row.get("bb_lower", 0) * 1.02:
        score += 1.5

    # ROC positive
    if row.get("roc", 0) > 0:
        score += min(row.get("roc", 0) / 5, 2.0)

    return score


def _score_sell_signal(row: pd.Series) -> float:
    """Score a stock for sell signal (higher = stronger sell)."""
    score = 0.0

    # RSI: overbought
    if row.get("rsi", 50) > 70:
        score += 2.0
    elif row.get("rsi", 50) < 30:
        score -= 1.0  # oversold - not sell

    # Stochastic: bearish crossover
    if row.get("stoch_k", 50) < row.get("stoch_d", 50) and row.get("stoch_k", 50) > 70:
        score += 2.0

    # MACD: bearish momentum
    if row.get("macd", 0) < row.get("macd_signal", 0) and row.get("macd_hist", 0) < 0:
        score += 2.0

    # Price below moving averages (downtrend)
    if row.get("Close", 0) < row.get("sma_20", 0) < row.get("sma_50", 0):
        score += 2.0

    # Negative momentum
    momentum_10d = row.get("momentum_10d", 0)
    momentum_21d = row.get("momentum_21d", 0)
    if momentum_10d < 0 and momentum_21d < 0:
        score += min(abs(momentum_10d + momentum_21d), 4.0)

    # ADX: strong downtrend
    adx = row.get("adx", 0)
    if 25 <= adx <= 40:
        score += 1.5

    # Price near upper Bollinger Band (resistance)
    if row.get("Close", 0) >= row.get("bb_upper", 0) * 0.98:
        score += 1.5

    # ROC negative
    if row.get("roc", 0) < 0:
        score += min(abs(row.get("roc", 0)) / 5, 2.0)

    return score


async def get_swing_predictions(
    universe: str | None = None,
    top_n: int = 10,
    period: str = "450d",
    force_refresh: bool = False,
) -> dict:
    """Get momentum-based swing trade predictions.

    Analyzes technical indicators to predict 10 buy and 10 sell candidates
    for 2-week to 1-month swing trades based on previous momentum.
    """
    symbols = [s.strip().upper() for s in universe.split(",")] if universe else list(SWING_WATCHLIST)
    symbols = [s for s in symbols if s]
    logger.info("calculating swing trade predictions for %d symbols", len(symbols))

    # Download enough data for 200-day SMA (typically ~300 trading days = ~15 months)
    end_date = date.today()
    lookback_days = 450
    if period.endswith("d") and period[:-1].isdigit():
        lookback_days = max(60, min(1000, int(period[:-1])))
    start_date = end_date - timedelta(days=lookback_days)

    buy_candidates = []
    sell_candidates = []
    analysis_data = {}

    async def analyze_symbol(symbol: str) -> Optional[tuple]:
        """Fetch and analyze a single symbol."""
        try:
            # Run synchronous yfinance in a thread pool
            loop = asyncio.get_running_loop()
            async with _YF_SEMAPHORE:
                await asyncio.sleep(0.25)
                df = await loop.run_in_executor(
                    None,
                    lambda: yf.Ticker(symbol).history(start=start_date, end=end_date, interval="1d")
                )

            if df.empty or len(df) < 50:
                return None

            df = _calculate_indicators(df)
            latest = df.iloc[-1]

            # Skip if missing critical indicators
            if pd.isna(latest.get("rsi")) or pd.isna(latest.get("adx")):
                return None

            # Calculate scores
            buy_score = _score_buy_signal(latest)
            sell_score = _score_sell_signal(latest)

            # Store analysis
            analysis_data[symbol] = {
                "price": round(latest["Close"], 2),
                "rsi": round(latest["rsi"], 1),
                "macd": round(latest["macd"], 4),
                "macd_signal": round(latest["macd_signal"], 4),
                "macd_hist": round(latest["macd_hist"], 4),
                "stoch_k": round(latest["stoch_k"], 1),
                "stoch_d": round(latest["stoch_d"], 1),
                "adx": round(latest["adx"], 1),
                "sma_20": round(latest["sma_20"], 2),
                "sma_50": round(latest["sma_50"], 2),
                "momentum_10d": round(latest["momentum_10d"], 2),
                "momentum_21d": round(latest["momentum_21d"], 2),
                "atr": round(latest["atr"], 2),
                "bb_upper": round(latest["bb_upper"], 2),
                "bb_lower": round(latest["bb_lower"], 2),
                "volume_ratio": round(latest["volume_ratio"], 2),
                "buy_score": round(buy_score, 2),
                "sell_score": round(sell_score, 2),
            }

            # Add to candidates
            if buy_score > 0:
                buy_candidates.append({
                    "symbol": symbol,
                    "score": round(buy_score, 2),
                    "price": round(latest["Close"], 2),
                    "rsi": round(latest["rsi"], 1),
                    "momentum_10d": round(latest["momentum_10d"], 2),
                    "momentum_21d": round(latest["momentum_21d"], 2),
                    "adx": round(latest["adx"], 1),
                    "reason": _get_buy_reason(latest),
                })

            if sell_score > 0:
                sell_candidates.append({
                    "symbol": symbol,
                    "score": round(sell_score, 2),
                    "price": round(latest["Close"], 2),
                    "rsi": round(latest["rsi"], 1),
                    "momentum_10d": round(latest["momentum_10d"], 2),
                    "momentum_21d": round(latest["momentum_21d"], 2),
                    "adx": round(latest["adx"], 1),
                    "reason": _get_sell_reason(latest),
                })
            return None

        except Exception as e:
            logger.warning("error analyzing %s: %s", symbol, e)
            return None

    # Fetch all symbols concurrently (rate-limited by yfinance semaphore)
    await asyncio.gather(*[analyze_symbol(symbol) for symbol in symbols], return_exceptions=True)

    # Sort and take top 10 for each
    buy_candidates.sort(key=lambda x: x["score"], reverse=True)
    sell_candidates.sort(key=lambda x: x["score"], reverse=True)

    top_buys = buy_candidates[:top_n]
    top_sells = sell_candidates[:top_n]

    return {
        "date": str(date.today()),
        "universe": symbols,
        "period": period,
        "force_refresh": force_refresh,
        "horizon": "2 weeks to 1 month",
        "methodology": "Technical indicators (RSI, Stochastic, MACD, ADX, Bollinger Bands) + momentum (10d, 21d rate of change)",
        "buy_candidates": top_buys,
        "sell_candidates": top_sells,
        "total_analyzed": len(analysis_data),
        "analysis": analysis_data,
    }


def _get_buy_reason(row: pd.Series) -> str:
    """Generate buy reason string."""
    reasons = []

    if row.get("rsi", 50) < 40:
        reasons.append(f"RSI oversold ({row['rsi']:.0f})")
    if row.get("macd", 0) > row.get("macd_signal", 0):
        reasons.append("MACD bullish crossover")
    if row.get("Close", 0) > row.get("sma_20", 0):
        reasons.append("Price above 20-day MA")
    if row.get("momentum_10d", 0) > 0:
        reasons.append(f"+{row['momentum_10d']:.1f}% 10d momentum")
    if row.get("stoch_k", 50) < 20:
        reasons.append("Stochastic oversold")
    if row.get("adx", 0) > 25:
        reasons.append(f"Strong trend (ADX {row['adx']:.0f})")

    return "; ".join(reasons[:3]) if reasons else "Momentum setup"


def _get_sell_reason(row: pd.Series) -> str:
    """Generate sell reason string."""
    reasons = []

    if row.get("rsi", 50) > 60:
        reasons.append(f"RSI overbought ({row['rsi']:.0f})")
    if row.get("macd", 0) < row.get("macd_signal", 0):
        reasons.append("MACD bearish crossover")
    if row.get("Close", 0) < row.get("sma_20", 0):
        reasons.append("Price below 20-day MA")
    if row.get("momentum_10d", 0) < 0:
        reasons.append(f"{row['momentum_10d']:.1f}% 10d momentum")
    if row.get("stoch_k", 50) > 80:
        reasons.append("Stochastic overbought")
    if row.get("adx", 0) > 25 and row.get("momentum_10d", 0) < 0:
        reasons.append(f"Downtrend (ADX {row['adx']:.0f})")

    return "; ".join(reasons[:3]) if reasons else "Momentum setup"
