"""Smoke tests for the shipped IslamicSpotStrategy (loads, computes, long-only)."""

from pathlib import Path

import numpy as np
from pandas import DataFrame, date_range

from freqtrade.resolvers import StrategyResolver


_STRATEGY_PATH = str(Path(__file__).resolve().parents[2] / "user_data" / "strategies")


def _make_ohlcv(rows: int = 320) -> DataFrame:
    """A deterministic gently-trending OHLCV frame with enough history."""
    idx = date_range("2024-01-01", periods=rows, freq="1h", tz="UTC")
    # Smooth uptrend with mild oscillation so indicators and signals can form.
    trend = np.linspace(100, 130, rows)
    wave = np.sin(np.linspace(0, 20, rows)) * 2
    close = trend + wave
    df = DataFrame(
        {
            "date": idx,
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.linspace(1000, 2000, rows),
        }
    )
    return df


def _load():
    conf = {
        "strategy": "IslamicSpotStrategy",
        "strategy_path": _STRATEGY_PATH,
        "timeframe": "1h",
        "trading_mode": "spot",
        "stake_currency": "USDT",
        "stake_amount": 50,
        "user_data_dir": Path(_STRATEGY_PATH).parent,
    }
    return StrategyResolver.load_strategy(conf)


def test_strategy_loads_and_is_long_only() -> None:
    strat = _load()
    assert strat.can_short is False
    assert strat.timeframe == "1h"
    assert strat.stoploss < 0


def test_populate_indicators_and_signals() -> None:
    strat = _load()
    meta = {"pair": "BTC/USDT"}
    df = strat.populate_indicators(_make_ohlcv(), meta)
    for col in ("ema_fast", "ema_slow", "rsi", "adx", "volume_ma"):
        assert col in df.columns

    df = strat.populate_entry_trend(df, meta)
    df = strat.populate_exit_trend(df, meta)
    assert "enter_long" in df.columns
    assert "exit_long" in df.columns
    # No short columns are ever produced.
    assert "enter_short" not in df.columns or df.get("enter_short", 0).sum() == 0
    # Signals are 0/1 integers where set.
    assert set(df["enter_long"].dropna().unique()).issubset({0, 1})
