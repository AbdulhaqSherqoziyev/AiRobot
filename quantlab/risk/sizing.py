"""Position sizing from a strategy's risk config, shared by backtest, paper and live so a
result on one can carry over to the next."""

from __future__ import annotations

import numpy as np
import pandas as pd

LOOKBACK_DAYS = 30
HISTORY_DAYS = LOOKBACK_DAYS + 10  # candles an engine must hand in for a fully warm estimate


def vol_target_stake(df: pd.DataFrame, target_daily_vol: float = 0.015, lookback_days: int = LOOKBACK_DAYS, max_stake: float = 0.95) -> np.ndarray:
    """Position fraction aiming for a fixed daily volatility, from fully closed days only.
    While volatility is still unknown the stake is the minimum, not the maximum."""
    daily = pd.Series(df["close"].to_numpy(), index=df["ts"].to_numpy() // 86400).groupby(level=0).last()
    vol = daily.pct_change().rolling(lookback_days, min_periods=lookback_days).std().shift(1)
    stake = (target_daily_vol / vol).clip(upper=max_stake).fillna(0.1)
    return stake.reindex(df["ts"].to_numpy() // 86400).to_numpy(dtype=float)


def stake_series(df: pd.DataFrame, risk: dict | None) -> np.ndarray | None:
    """Per-candle stake, or None for the fixed `stake_pct`."""
    sizing = (risk or {}).get("sizing")
    if not sizing or sizing.get("mode") != "vol_target":
        return None
    return vol_target_stake(df, float(sizing.get("target", 0.015)), max_stake=float((risk or {}).get("stake_pct", 0.95)))
