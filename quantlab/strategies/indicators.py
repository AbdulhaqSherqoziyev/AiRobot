"""Causal indicators in pandas. Each value at i depends only on candles up to i."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    return out.where(dn != 0, 100.0).where(up.notna())


def macd(c: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    m = ema(c, fast) - ema(c, slow)
    sig = m.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return m, sig, m - sig


def bollinger(c: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(c, n)
    sd = c.rolling(n, min_periods=n).std(ddof=0)
    return mid - k * sd, mid, mid + k * sd


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift()
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def stoch_rsi(c: pd.Series, n: int = 14, k: int = 3, d: int = 3) -> tuple[pd.Series, pd.Series]:
    r = rsi(c, n)
    lo, hi = r.rolling(n, min_periods=n).min(), r.rolling(n, min_periods=n).max()
    st = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    ks = st.rolling(k, min_periods=k).mean()
    return ks, ks.rolling(d, min_periods=d).mean()


def adx(df: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up, dn = df["high"].diff(), -df["low"].diff()
    plus = up.where((up > dn) & (up > 0), 0.0)
    minus = dn.where((dn > up) & (dn > 0), 0.0)
    a = atr(df, n)
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / a
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean(), pdi, mdi


def rolling_vwap(df: pd.DataFrame, n: int = 48) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    v = df["volume"]
    return (tp * v).rolling(n, min_periods=n).sum() / v.rolling(n, min_periods=n).sum().replace(0, np.nan)


def supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0) -> pd.Series:
    """True while in an uptrend."""
    a = atr(df, n).to_numpy()
    hl2 = ((df["high"] + df["low"]) / 2).to_numpy()
    c = df["close"].to_numpy()
    upper = hl2 + mult * a
    lower = hl2 - mult * a
    trend = np.zeros(len(df), dtype=bool)
    for i in range(1, len(df)):
        if np.isnan(a[i]) or np.isnan(a[i - 1]):
            continue
        upper[i] = min(upper[i], upper[i - 1]) if c[i - 1] <= upper[i - 1] else upper[i]
        lower[i] = max(lower[i], lower[i - 1]) if c[i - 1] >= lower[i - 1] else lower[i]
        if c[i] > upper[i - 1]:
            trend[i] = True
        elif c[i] < lower[i - 1]:
            trend[i] = False
        else:
            trend[i] = trend[i - 1]
    return pd.Series(trend, index=df.index)
