"""VectorBT against the authoritative engine. These pin down where they agree and where they do
not; neither may be assumed from the other."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("vectorbt")

from conftest import synthetic  # noqa: E402
from quantlab.backtest.core import ExecConfig, Filters  # noqa: E402
from quantlab.backtest.engine import run_on_signals  # noqa: E402
from quantlab.research import vbt_adapter  # noqa: E402
from quantlab.research.sweep import SweepConfig, run_sweep  # noqa: E402
from quantlab.strategies.base import get_strategy  # noqa: E402

NO_MIN = Filters(min_notional=0.0)


def both_tf(df, enter, exit_, cfg, tf):
    return run_on_signals(df, enter, exit_, tf, 100.0, cfg), vbt_adapter.simulate(df, enter[:, None], exit_[:, None], tf, cfg, 100.0)[0]


def both(df, enter, exit_, cfg):
    return both_tf(df, enter, exit_, cfg, "4h")


def signals(key, df, params=None):
    s = get_strategy(key).signals(df, params)
    return s["enter"].to_numpy(), s["exit"].to_numpy()


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("key,params", [("rsi_ema_trend", {"rsi_period": 7, "rsi_entry": 50, "rsi_exit": 55, "ema_fast": 5, "ema_slow": 30}), ("ema_crossover", {"fast": 12, "slow": 26}), ("rsi_reversal", {})])
def test_equal_on_fills_fees_and_equity_without_stops(seed, key, params):
    """Next-open fills, percentage fees and slippage, fraction of cash: identical accounting."""
    df = synthetic(2000, seed=seed, step=14400)
    e, x = signals(key, df, params)
    native, fast = both(df, e, x, ExecConfig(fee=0.001, slippage=0.0005, stake_pct=0.95, filters=NO_MIN))
    assert native.metrics["total_trades"] > 3
    assert fast["total_trades"] == native.metrics["total_trades"]
    for k in ("final_balance", "max_drawdown", "fees_paid", "win_rate"):
        assert fast[k] == pytest.approx(native.metrics[k], abs=1e-3), k


@pytest.mark.parametrize("key,params", [("rsi_ema_trend", {"rsi_period": 7, "rsi_entry": 35, "rsi_exit": 65, "ema_fast": 5, "ema_slow": 30}), ("ema_crossover", {"fast": 12, "slow": 26})])
def test_equal_on_real_binance_candles(key, params):
    d = json.loads((Path(__file__).parent / "fixtures" / "jesse" / "jesse_results.json").read_text())
    df = pd.DataFrame(d["hourly_candles"], columns=["ts", "open", "high", "low", "close", "volume"])
    e, x = signals(key, df, params)
    native, fast = both_tf(df, e, x, ExecConfig(fee=0.001, slippage=0.0005, stake_pct=0.95, filters=Filters(min_notional=5.0)), "1h")
    assert native.metrics["total_trades"] > 3 and fast["total_trades"] == native.metrics["total_trades"]
    assert fast["total_return"] == pytest.approx(native.metrics["total_return"], abs=1e-3)


def test_signal_timing_is_next_open_in_both():
    df = synthetic(300, seed=4, step=14400)
    e, x = np.zeros(300, bool), np.zeros(300, bool)
    e[50], x[100] = True, True
    native, fast = both(df, e, x, ExecConfig(fee=0, slippage=0, stake_pct=1.0, filters=NO_MIN))
    assert native.trades[0]["entry_price"] == df["open"].iloc[51] and native.trades[0]["exit_price"] == df["open"].iloc[101]
    assert fast["final_balance"] == pytest.approx(native.metrics["final_balance"], abs=1e-6)


def test_same_candle_conflicts_follow_the_engine_rule():
    df = synthetic(300, seed=5, step=14400)
    e, x = np.zeros(300, bool), np.zeros(300, bool)
    e[50], x[50] = True, True  # flat: enter
    e[100], x[100] = True, True  # in position: exit
    e[150], x[150] = True, True  # flat: enter
    x[200] = True
    native, fast = both(df, e, x, ExecConfig(fee=0.001, slippage=0.0005, stake_pct=0.95, filters=NO_MIN))
    assert native.metrics["total_trades"] == fast["total_trades"] == 2
    assert fast["final_balance"] == pytest.approx(native.metrics["final_balance"], abs=1e-6)


def test_known_difference_lot_rounding_is_only_in_the_engine():
    """The adapter skips VectorBT's size_granularity, which leaves dust and blocks later entries.
    Unrounded sizes cost a small gap and keep the trades identical."""
    d = json.loads((Path(__file__).parent / "fixtures" / "jesse" / "jesse_results.json").read_text())
    df = pd.DataFrame(d["hourly_candles"], columns=["ts", "open", "high", "low", "close", "volume"])
    e, x = signals("ema_crossover", df, {"fast": 12, "slow": 26})
    native, fast = both_tf(df, e, x, ExecConfig(fee=0.001, slippage=0.0005, stake_pct=0.95, filters=Filters(min_notional=5.0, step_size=0.00001)), "1h")
    assert fast["total_trades"] == native.metrics["total_trades"] == 44
    assert fast["total_return"] != native.metrics["total_return"]
    assert fast["total_return"] == pytest.approx(native.metrics["total_return"], abs=0.2)


def test_known_difference_minimum_order_is_only_in_the_engine():
    df = synthetic(300, seed=6, step=14400)
    e, x = signals("rsi_reversal", df)
    cfg = ExecConfig(fee=0.001, slippage=0.0005, stake_pct=0.95, filters=Filters(min_notional=500.0))
    native, fast = both(df, e, x, cfg)
    assert native.metrics["total_trades"] == 0 and native.rejected
    assert fast["total_trades"] >= 1


@pytest.mark.parametrize("seed", [1, 2])
def test_known_difference_stops_are_close_not_equal(seed):
    """Gaps and same-candle ordering differ, so stop runs get a tolerance, not equality."""
    df = synthetic(2000, seed=seed, step=14400)
    e, x = signals("ema_crossover", df, {"fast": 12, "slow": 26})
    native, fast = both(df, e, x, ExecConfig(fee=0.001, slippage=0.0005, stake_pct=0.95, stoploss_pct=0.03, filters=NO_MIN))
    assert fast["total_trades"] == pytest.approx(native.metrics["total_trades"], abs=3)
    assert fast["total_return"] == pytest.approx(native.metrics["total_return"], abs=10)


def test_sweep_reports_engine_gap_and_backends_agree_on_the_choice():
    frames = {"AAA/USDT": synthetic(3000, seed=9, step=14400)}
    start = int(frames["AAA/USDT"]["ts"].iloc[200])
    grid = {"rsi_period": [7, 14], "rsi_entry": [30, 35], "rsi_exit": [65, 70], "ema_fast": [5], "ema_slow": [30]}
    strat = get_strategy("rsi_ema_trend")
    fast = run_sweep(frames, strat, grid, "4h", start, SweepConfig(backend="vectorbt", min_trades=3))
    slow = run_sweep(frames, strat, grid, "4h", start, SweepConfig(backend="native", min_trades=3))
    assert fast["summary"]["selected"] == slow["summary"]["selected"]
    if fast["summary"]["selected"]:
        assert fast["summary"]["engine_gap_max_pct"] < 1.0
        assert fast["summary"]["test_by_pair"] == slow["summary"]["test_by_pair"]  # authoritative numbers come from the same engine
    assert fast["repro"]["vectorbt"] == vbt_adapter.available()
