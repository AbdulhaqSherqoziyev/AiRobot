"""Overlays tested on top of strategies. All are causal: the value at candle i uses only
data available when candle i closed, and daily values only from fully closed days."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantlab.risk.sizing import vol_target_stake  # noqa: F401  re-exported for the studies
from quantlab.strategies import indicators as ind


def _daily_close(df: pd.DataFrame) -> pd.Series:
    day = df["ts"].to_numpy() // 86400
    return pd.Series(df["close"].to_numpy(), index=day).groupby(level=0).last()


def uptrend(df: pd.DataFrame, ema_days: int = 200) -> np.ndarray:
    """True while the last fully closed day closed above its daily EMA."""
    daily = _daily_close(df)
    above = (daily > ind.ema(daily, ema_days)).shift(1, fill_value=False)  # shift: closed days only
    return above.reindex(df["ts"].to_numpy() // 86400).to_numpy(dtype=bool)
