"""Pure-sync technical analysis primitives — called via asyncio.to_thread from main.py.

Signal inventory per full_analysis() call (leaf values, non-None):
  rsi (3) · macd_std (4) · macd_fast (4) · bollinger_std (5) · bollinger_tight (5)
  atr (3) · sma (6) · sma_signals (5) · ema (3) · ema_signals (2) · stochastic (3)
  williams_r (1) · cci (1) · adx (5) · mfi (1) · obv (2) · volume (2) · cmf (1)
  vwap (2) · momentum_10 (1) · roc (3) · pivots (7) · fibonacci (7)
  fib_extensions (4) · signal (3)
  ─────────────────────────────────────────────────────────────────────────
  Total: ~79 per timeframe (fewer for short periods: SMA-50/100/200 need more bars)

/analyze fetches 4 timeframes (1mo, 3mo, 6mo, 1y) → 4 × ~79 ≈ 300–316 signals.
"""
import math
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm


# ── Utilities ─────────────────────────────────────────────────────────────────

def _f(val: Any, decimals: int = 4) -> float | None:
    """Return None for NaN/inf/None, else round to `decimals` places."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, decimals)
    except (TypeError, ValueError):
        return None


# ── Data Fetching ─────────────────────────────────────────────────────────────

def fetch(symbol: str, period: str = "3mo") -> pd.DataFrame:
    """Fetch OHLCV history via yfinance. Raises ValueError if symbol is unknown."""
    df = yf.Ticker(symbol.upper()).history(period=period)
    if df.empty:
        raise ValueError(f"No market data found for symbol '{symbol}'")
    return df


# ── Momentum Oscillators ──────────────────────────────────────────────────────

def rsi(close: pd.Series, period: int = 14) -> float | None:
    """Wilder's RSI (EWM com=period-1 → alpha=1/period)."""
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.where(loss != 0, np.nan)
    return _f((100 - 100 / (1 + rs)).iloc[-1], 2)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, sig_span: int = 9) -> dict:
    """MACD with configurable spans. Defaults: standard 12/26/9."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line     = ema_fast - ema_slow
    signal   = line.ewm(span=sig_span, adjust=False).mean()
    hist     = line - signal
    h = _f(hist.iloc[-1])
    return {
        "line":      _f(line.iloc[-1]),
        "signal":    _f(signal.iloc[-1]),
        "histogram": h,
        "trend":     "bullish" if (h or 0) > 0 else "bearish",
    }


def stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> dict:
    """Stochastic oscillator (%K and %D)."""
    lo  = df["Low"].rolling(k_period).min()
    hi  = df["High"].rolling(k_period).max()
    rng = (hi - lo).replace(0, np.nan)
    k   = 100 * (df["Close"] - lo) / rng
    d   = k.rolling(d_period).mean()
    kv  = _f(k.iloc[-1], 2) or 50.0
    return {
        "k":      kv,
        "d":      _f(d.iloc[-1], 2),
        "signal": "overbought" if kv > 80 else "oversold" if kv < 20 else "neutral",
    }


def williams_r(df: pd.DataFrame, period: int = 14) -> float | None:
    """Williams %R. Range: −100 (oversold) to 0 (overbought)."""
    hi  = df["High"].rolling(period).max()
    lo  = df["Low"].rolling(period).min()
    rng = (hi - lo).replace(0, np.nan)
    return _f(((hi - df["Close"]) / rng * -100).iloc[-1], 2)


def cci(df: pd.DataFrame, period: int = 20) -> float | None:
    """Commodity Channel Index. ±100 = normal range, ±200 = extreme."""
    tp  = (df["High"] + df["Low"] + df["Close"]) / 3
    ma  = tp.rolling(period).mean()
    md  = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    val = (tp - ma) / (0.015 * md.replace(0, np.nan))
    return _f(val.iloc[-1], 2)


def mfi(df: pd.DataFrame, period: int = 14) -> float | None:
    """Money Flow Index — volume-weighted RSI. <20 oversold, >80 overbought."""
    tp  = (df["High"] + df["Low"] + df["Close"]) / 3
    mf  = tp * df["Volume"]
    pos = mf.where(tp > tp.shift(), 0.0).rolling(period).sum()
    neg = mf.where(tp <= tp.shift(), 0.0).rolling(period).sum()
    mfr = pos / neg.replace(0, np.nan)
    return _f((100 - 100 / (1 + mfr)).iloc[-1], 2)


def roc(close: pd.Series, period: int = 10) -> float | None:
    """Rate of Change (%). Positive = upward momentum."""
    shifted = close.shift(period)
    return _f(((close - shifted) / shifted.replace(0, np.nan) * 100).iloc[-1], 2)


def momentum_osc(close: pd.Series, period: int = 10) -> float | None:
    """Raw price momentum: close − close[period bars ago]."""
    if len(close) <= period:
        return None
    return _f(float(close.iloc[-1]) - float(close.iloc[-(period + 1)]))


# ── Trend Indicators ──────────────────────────────────────────────────────────

def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> dict:
    """Bollinger Bands. position: 0 = lower band, 1 = upper band."""
    ma    = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = ma + num_std * std
    lower = ma - num_std * std
    price = float(close.iloc[-1])
    bw    = (_f(upper.iloc[-1]) or 0) - (_f(lower.iloc[-1]) or 0)
    ma_f  = _f(ma.iloc[-1]) or 1.0
    pos   = (price - (_f(lower.iloc[-1]) or price)) / bw if bw > 0 else 0.5
    return {
        "upper":    _f(upper.iloc[-1]),
        "middle":   _f(ma.iloc[-1]),
        "lower":    _f(lower.iloc[-1]),
        "position": round(pos, 3),
        "squeeze":  (bw / ma_f < 0.05) if ma_f > 0 else False,
    }


def atr(df: pd.DataFrame, period: int = 14) -> float | None:
    """Average True Range (Wilder's EWM smoothing)."""
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"]  - df["Close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return _f(tr.ewm(com=period - 1, adjust=False).mean().iloc[-1])


def adx(df: pd.DataFrame, period: int = 14) -> dict:
    """Average Directional Index + ±DI. ADX > 25 = strong trend."""
    up   = df["High"].diff()
    down = -df["Low"].diff()
    dm_p = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    dm_n = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr   = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"]  - df["Close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr_s = tr.ewm(com=period - 1, adjust=False).mean().replace(0, np.nan)
    di_p  = 100 * dm_p.ewm(com=period - 1, adjust=False).mean() / atr_s
    di_n  = 100 * dm_n.ewm(com=period - 1, adjust=False).mean() / atr_s
    dx    = 100 * (di_p - di_n).abs() / (di_p + di_n).replace(0, np.nan)
    adxv  = dx.ewm(com=period - 1, adjust=False).mean()
    av    = _f(adxv.iloc[-1], 2) or 0.0
    dp    = _f(di_p.iloc[-1],  2) or 0.0
    dn    = _f(di_n.iloc[-1],  2) or 0.0
    return {
        "adx":            av,
        "di_plus":        dp,
        "di_minus":       dn,
        "trend_strength": "strong" if av > 25 else "weak" if av < 20 else "moderate",
        "direction":      "bullish" if dp > dn else "bearish",
    }


def sma(close: pd.Series, period: int) -> float | None:
    """Simple Moving Average. Returns None when fewer than `period` bars exist."""
    if len(close) < period:
        return None
    return _f(close.rolling(period).mean().iloc[-1])


def ema(close: pd.Series, period: int) -> float | None:
    """Exponential Moving Average."""
    return _f(close.ewm(span=period, adjust=False).mean().iloc[-1])


# ── Volume Indicators ─────────────────────────────────────────────────────────

def obv_indicator(df: pd.DataFrame) -> dict:
    """On-Balance Volume. Positive slope = accumulation, negative = distribution."""
    direction = df["Close"].diff().apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
    series    = (df["Volume"] * direction).cumsum()
    lookback  = min(20, len(series))
    slope     = float(series.iloc[-1] - series.iloc[-lookback]) if lookback > 1 else 0.0
    return {
        "value": _f(series.iloc[-1], 0),
        "trend": "accumulation" if slope > 0 else "distribution",
    }


def cmf(df: pd.DataFrame, period: int = 20) -> float | None:
    """Chaikin Money Flow. >0.1 bullish, <−0.1 bearish."""
    rng     = (df["High"] - df["Low"]).replace(0, np.nan)
    clv     = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / rng
    vol_sum = df["Volume"].rolling(period).sum().replace(0, np.nan)
    return _f((clv * df["Volume"]).rolling(period).sum().iloc[-1] / float(vol_sum.iloc[-1]))


def volume_signals(df: pd.DataFrame) -> dict:
    """Current vs 20-day average volume. ratio > 2 = surge."""
    avg   = float(df["Volume"].rolling(20).mean().iloc[-1]) or 1.0
    cur   = float(df["Volume"].iloc[-1])
    ratio = round(cur / avg, 2)
    return {"ratio": ratio, "surge": ratio > 2.0}


# ── Structural Indicators ─────────────────────────────────────────────────────

def approx_vwap(df: pd.DataFrame, period: int = 20) -> dict:
    """Rolling 20-day VWAP proxy from daily OHLCV (no intraday data needed)."""
    tp      = (df["High"] + df["Low"] + df["Close"]) / 3
    vol_sum = df["Volume"].rolling(period).sum().replace(0, np.nan)
    v       = _f((tp * df["Volume"]).rolling(period).sum().iloc[-1] / float(vol_sum.iloc[-1]))
    price   = float(df["Close"].iloc[-1])
    return {"value": v, "above_vwap": price > (v or price)}


def pivot_points(df: pd.DataFrame) -> dict:
    """Classic floor pivot points from the prior completed session bar."""
    i  = -2 if len(df) > 1 else -1
    h  = float(df["High"].iloc[i])
    lo = float(df["Low"].iloc[i])
    c  = float(df["Close"].iloc[i])
    pp = (h + lo + c) / 3
    return {
        "pp": _f(pp),        "r1": _f(2*pp - lo),  "r2": _f(pp + h - lo),   "r3": _f(h + 2*(pp - lo)),
        "s1": _f(2*pp - h),  "s2": _f(pp - h + lo), "s3": _f(lo - 2*(h - pp)),
    }


def annual_vol(close: pd.Series) -> float:
    """Annualised historical volatility (252 trading-day convention)."""
    return float(close.pct_change().dropna().std() * math.sqrt(252))


# ── Fibonacci ─────────────────────────────────────────────────────────────────

def fibonacci_levels(high: float, low: float) -> dict[str, float]:
    """Retracement levels (0% = high, 100% = low)."""
    d = high - low
    return {
        "0.0":   round(high, 4),           "23.6": round(high - d * .236, 4),
        "38.2":  round(high - d * .382, 4),"50.0": round(high - d * .500, 4),
        "61.8":  round(high - d * .618, 4),"78.6": round(high - d * .786, 4),
        "100.0": round(low, 4),
    }


def fibonacci_extensions(high: float, low: float) -> dict[str, float]:
    """Extension levels above swing high (continuation targets)."""
    d = high - low
    return {
        "127.2": round(high + d * .272, 4), "138.2": round(high + d * .382, 4),
        "161.8": round(high + d * .618, 4), "261.8": round(high + d * 1.618, 4),
    }


# ── Position Sizing & Options ─────────────────────────────────────────────────

def kelly_fraction(win_rate: float, avg_win_r: float = 2.0, avg_loss_r: float = 1.0) -> float:
    """Half-Kelly fraction of capital per trade. Capped at 25%."""
    b = avg_win_r / avg_loss_r
    q = 1.0 - win_rate
    return round(max(0.0, min((b * win_rate - q) / b / 2, 0.25)), 4)


def bs_greeks(
    S: float, K: float, T: float, r: float, sigma: float, *, call: bool = True
) -> dict:
    """Black-Scholes price and Greeks. theta per day, vega per 1% vol move."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {"price": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    st  = math.sqrt(T)
    d1  = (math.log(S / K) + (r + .5 * sigma ** 2) * T) / (sigma * st)
    d2  = d1 - sigma * st
    dis = math.exp(-r * T)
    n1, n2 = norm.cdf(d1), norm.cdf(d2)
    if call:
        price = S * n1 - K * dis * n2
        delta = n1
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * st) - r * K * dis * n2) / 365
    else:
        price = K * dis * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = n1 - 1.0
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * st) + r * K * dis * norm.cdf(-d2)) / 365
    return {
        "price": round(price, 4), "delta": round(delta, 4),
        "gamma": round(norm.pdf(d1) / (S * sigma * st), 6),
        "theta": round(theta, 4), "vega":  round(S * norm.pdf(d1) * st / 100, 4),
    }


# ── Composite Scoring ─────────────────────────────────────────────────────────

def score_signals(
    rsi14: float | None, rsi9: float | None,
    macd_std: dict, macd_fast: dict, bb_std: dict,
    stoch: dict, wpr: float | None, cci_val: float | None,
    adx_data: dict, obv_data: dict, cmf_val: float | None, mfi_val: float | None,
) -> dict:
    """12-indicator composite score. Range: −14 to +14.

    Thresholds: ≥6 STRONG BUY · ≥3 BUY · ≤−6 STRONG SELL · ≤−3 SELL · else HOLD.
    """
    score = 0
    reasons: list[str] = []

    def _add(cond: bool, pts: int, label: str) -> None:
        nonlocal score
        if cond:
            score += pts
            reasons.append(label)

    r14 = rsi14 or 50.0
    _add(r14 < 30,        +2, "RSI-14 oversold")
    _add(30 <= r14 < 45,  +1, "RSI-14 low")
    _add(r14 > 70,        -2, "RSI-14 overbought")
    _add(55 < r14 <= 70,  -1, "RSI-14 elevated")

    r9 = rsi9 or 50.0
    _add(r9 < 30, +1, "RSI-9 oversold confirm")
    _add(r9 > 70, -1, "RSI-9 overbought confirm")

    hs = macd_std.get("histogram") or 0.0
    _add(hs > 0,  +1, "MACD bullish")
    _add(hs <= 0, -1, "MACD bearish")

    hf = macd_fast.get("histogram") or 0.0
    _add(hf > 0,  +1, "MACD-fast bullish")
    _add(hf <= 0, -1, "MACD-fast bearish")

    pos = bb_std.get("position") or 0.5
    _add(pos < 0.2,              +1, "near lower BB")
    _add(pos > 0.8,              -1, "near upper BB")
    _add(bool(bb_std.get("squeeze")), +1, "BB squeeze (breakout pending)")

    sk = stoch.get("k") or 50.0
    _add(sk < 20, +1, "Stoch oversold")
    _add(sk > 80, -1, "Stoch overbought")

    wr = wpr or -50.0
    _add(wr < -80, +1, "Williams %R oversold")
    _add(wr > -20, -1, "Williams %R overbought")

    cv = cci_val or 0.0
    _add(cv < -100, +1, "CCI oversold")
    _add(cv >  100, -1, "CCI overbought")

    av = adx_data.get("adx") or 0.0
    _add(av > 25 and adx_data.get("direction") == "bullish", +1, "strong uptrend (ADX)")
    _add(av > 25 and adx_data.get("direction") == "bearish", -1, "strong downtrend (ADX)")

    _add(obv_data.get("trend") == "accumulation", +1, "OBV accumulation")
    _add(obv_data.get("trend") == "distribution", -1, "OBV distribution")

    cf = cmf_val or 0.0
    _add(cf >  0.1, +1, "CMF positive flow")
    _add(cf < -0.1, -1, "CMF negative flow")

    mf = mfi_val or 50.0
    _add(mf < 20, +1, "MFI oversold")
    _add(mf > 80, -1, "MFI overbought")

    if score >= 6:    label = "STRONG BUY"   # noqa: E271
    elif score >= 3:  label = "BUY"           # noqa: E271
    elif score <= -6: label = "STRONG SELL"
    elif score <= -3: label = "SELL"
    else:             label = "HOLD"          # noqa: E271

    return {
        "signal":     label,
        "score":      score,
        "confidence": round(min(abs(score) / 10.0, 1.0), 2),
        "reasons":    reasons,
    }


def quick_score(df: pd.DataFrame) -> dict:
    """Convenience: compute full composite score directly from a DataFrame."""
    close = df["Close"]
    return score_signals(
        rsi(close, 14), rsi(close, 9),
        macd(close, 12, 26, 9), macd(close, 5, 13, 6),
        bollinger(close, 20, 2.0), stochastic(df),
        williams_r(df), cci(df), adx(df),
        obv_indicator(df), cmf(df), mfi(df),
    )


# ── Full Analysis (all indicators, single timeframe) ─────────────────────────

def full_analysis(df: pd.DataFrame) -> dict:
    """Run all ~79 indicators on a single OHLCV DataFrame.

    Returns nested dict. Signal counts per timeframe:
      1mo  ≈ 62  (SMA-50/100/200 unavailable — need ≥50/100/200 bars)
      3mo  ≈ 74  (SMA-100/200 unavailable — need ≥100/200 bars)
      6mo  ≈ 77  (SMA-200 unavailable — needs ≥200 bars / ~10mo)
      1y   ≈ 79  (all indicators available)
    4 timeframes combined → ~292–316 signals ≈ 300.
    """
    close = df["Close"]
    price = float(close.iloc[-1])

    # ── Oscillators ───────────────────────────────────────────────────────────
    rsi9  = rsi(close, 9)
    rsi14 = rsi(close, 14)
    rsi21 = rsi(close, 21)

    macd_std  = macd(close, 12, 26, 9)   # standard
    macd_fast = macd(close, 5, 13, 6)    # faster for early signals

    stoch_data = stochastic(df)
    wpr_val    = williams_r(df)
    cci_val    = cci(df)
    mfi_val    = mfi(df)

    roc5  = roc(close, 5)
    roc10 = roc(close, 10)
    roc20 = roc(close, 20)
    mom10 = momentum_osc(close, 10)

    # ── Trend ─────────────────────────────────────────────────────────────────
    bb_std   = bollinger(close, 20, 2.0)
    bb_tight = bollinger(close, 10, 1.5)

    atr7  = atr(df, 7)
    atr14 = atr(df, 14)
    atr21 = atr(df, 21)

    adx_data = adx(df)

    sma_vals = {
        "sma5":   sma(close, 5),   "sma10":  sma(close, 10),
        "sma20":  sma(close, 20),  "sma50":  sma(close, 50),
        "sma100": sma(close, 100), "sma200": sma(close, 200),
    }
    # Bool signals: None when the underlying SMA is unavailable
    def _gt(a: float | None, b: float | None) -> bool | None:
        return (a > b) if (a is not None and b is not None) else None  # noqa: E731

    sma_sigs = {
        "golden_cross":  _gt(sma_vals["sma50"],  sma_vals["sma200"]),
        "death_cross":   _gt(sma_vals["sma200"], sma_vals["sma50"]),
        "above_sma20":   _gt(price,              sma_vals["sma20"]),
        "above_sma50":   _gt(price,              sma_vals["sma50"]),
        "above_sma200":  _gt(price,              sma_vals["sma200"]),
    }

    ema_vals = {"ema9": ema(close, 9), "ema21": ema(close, 21), "ema50": ema(close, 50)}
    ema_sigs = {
        "ema9_above_ema21":  _gt(ema_vals["ema9"],  ema_vals["ema21"]),
        "price_above_ema21": _gt(price,             ema_vals["ema21"]),
    }

    # ── Volume ────────────────────────────────────────────────────────────────
    obv_data  = obv_indicator(df)
    vol_data  = volume_signals(df)
    cmf_val   = cmf(df)
    vwap_data = approx_vwap(df)

    # ── Structural ────────────────────────────────────────────────────────────
    high = float(df["High"].max())
    low_ = float(df["Low"].min())

    # ── Composite ─────────────────────────────────────────────────────────────
    sig = score_signals(
        rsi14, rsi9, macd_std, macd_fast, bb_std,
        stoch_data, wpr_val, cci_val, adx_data, obv_data, cmf_val, mfi_val,
    )

    return {
        "price":           round(price, 4),
        # Oscillators
        "rsi":             {"9": rsi9, "14": rsi14, "21": rsi21},
        "macd_std":        macd_std,
        "macd_fast":       macd_fast,
        "stochastic":      stoch_data,
        "williams_r":      wpr_val,
        "cci":             cci_val,
        "mfi":             mfi_val,
        "roc":             {"5": roc5, "10": roc10, "20": roc20},
        "momentum_10":     mom10,
        # Trend
        "bollinger_std":   bb_std,
        "bollinger_tight": bb_tight,
        "atr":             {"7": atr7, "14": atr14, "21": atr21},
        "adx":             adx_data,
        "sma":             sma_vals,
        "sma_signals":     sma_sigs,
        "ema":             ema_vals,
        "ema_signals":     ema_sigs,
        # Volume
        "obv":             obv_data,
        "volume":          vol_data,
        "cmf":             cmf_val,
        "vwap":            vwap_data,
        # Structural
        "pivots":          pivot_points(df),
        "fibonacci":       fibonacci_levels(high, low_),
        "fib_extensions":  fibonacci_extensions(high, low_),
        # Composite
        "signal":          sig,
    }


def fetch_and_analyze(symbol: str, period: str) -> dict:
    """Fetch + full_analysis in one synchronous call (safe for asyncio.to_thread)."""
    return full_analysis(fetch(symbol, period))


def consensus_signal(timeframes: dict[str, dict]) -> dict:
    """Aggregate directional signals across multiple timeframes.

    A signal is considered 'aligned' when ≥3 of 4 timeframes agree.
    """
    scores = [
        tf["signal"]["score"]
        for tf in timeframes.values()
        if isinstance(tf, dict) and "signal" in tf
    ]
    if not scores:
        return {"signal": "HOLD", "total_score": 0, "bullish_timeframes": 0, "bearish_timeframes": 0}
    total = sum(scores)
    bull  = sum(1 for s in scores if s > 0)
    bear  = sum(1 for s in scores if s < 0)

    if bull >= 3:    label = "STRONG BUY"  if total > 12 else "BUY"    # noqa: E271
    elif bear >= 3:  label = "STRONG SELL" if total < -12 else "SELL"
    elif bull > bear: label = "BUY"
    elif bear > bull: label = "SELL"
    else:             label = "HOLD"

    return {
        "signal":             label,
        "total_score":        total,
        "bullish_timeframes": bull,
        "bearish_timeframes": bear,
        "aligned_timeframes": max(bull, bear),
    }


# ── Sector Map ────────────────────────────────────────────────────────────────

SECTOR_MAP: dict[str, str] = {
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology",
    "META": "Technology", "NVDA": "Technology", "AMD":   "Technology",
    "CRM":  "Technology", "ADBE": "Technology", "INTC":  "Technology",
    "CRWD": "Technology", "STX":  "Technology", "SHOP":  "Technology",
    "AMZN": "Consumer",   "TSLA": "Consumer",   "NFLX":  "Consumer",
    "PYPL": "Consumer",
    "JPM":  "Financials", "BAC":  "Financials",
    "GLD":  "Commodities", "SLV": "Commodities", "USO":  "Commodities",
    "SPY":  "Index",       "QQQ": "Index",        "IWM":  "Index",
}
