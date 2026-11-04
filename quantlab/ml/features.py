"""Features and labels. Features look back only. Labels look forward, so they exist solely
in training, and the last `horizon` rows (whose label is unknown) are dropped."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantlab.strategies import indicators as ind


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    f = pd.DataFrame(index=df.index)
    for n in (1, 3, 6, 12, 24):
        f[f"ret_{n}"] = c.pct_change(n)
    f["rsi_14"] = ind.rsi(c, 14)
    f["ema_ratio_20_50"] = ind.ema(c, 20) / ind.ema(c, 50) - 1
    f["ema_ratio_50_200"] = ind.ema(c, 50) / ind.ema(c, 200) - 1
    f["atr_pct_14"] = ind.atr(df, 14) / c
    m, s, h = ind.macd(c)
    f["macd_hist_pct"] = h / c
    lo, mid, up = ind.bollinger(c, 20, 2.0)
    f["bb_width"] = (up - lo) / mid
    f["bb_pos"] = (c - lo) / (up - lo).replace(0, np.nan)
    adx, pdi, mdi = ind.adx(df, 14)
    f["adx_14"] = adx
    f["di_diff"] = pdi - mdi
    v = df["volume"]
    f["vol_z_24"] = (v - v.rolling(24).mean()) / v.rolling(24).std().replace(0, np.nan)
    f["vol_ret_24"] = c.pct_change().rolling(24).std()
    ts = pd.to_datetime(df["ts"], unit="s", utc=True)
    f["hour_sin"] = np.sin(2 * np.pi * ts.dt.hour.to_numpy() / 24)
    f["hour_cos"] = np.cos(2 * np.pi * ts.dt.hour.to_numpy() / 24)
    return f


def build_labels(df: pd.DataFrame, horizon: int = 6, cost: float = 0.003) -> pd.Series:
    """1 when the return `horizon` candles ahead beats round-trip costs."""
    fwd = df["close"].shift(-horizon) / df["close"] - 1
    return (fwd > cost).astype("float").where(fwd.notna())


def walk_forward_folds(n: int, folds: int = 4, min_train: float = 0.4, purge: int = 6) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window chronological folds. `purge` removes the training rows whose label
    window would overlap the test period, which would otherwise leak future returns."""
    start = int(n * min_train)
    size = (n - start) // folds
    out = []
    for k in range(folds):
        te_start = start + k * size
        te_end = te_start + size if k < folds - 1 else n
        out.append((np.arange(0, max(0, te_start - purge)), np.arange(te_start, te_end)))
    return out
