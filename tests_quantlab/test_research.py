import numpy as np
import pytest

from conftest import synthetic
from quantlab.backtest.core import ExecConfig, SimState, on_candle
from quantlab.backtest.engine import run_on_signals
from quantlab.research.filters import uptrend, vol_target_stake
from quantlab.research.walk_forward import folds, walk_forward
from quantlab.strategies.base import get_strategy


@pytest.fixture
def long_df():
    return synthetic(24 * 500, seed=3)


@pytest.mark.parametrize("fn", [uptrend, vol_target_stake])
def test_filters_do_not_look_ahead(long_df, fn):
    full = fn(long_df)
    for k in (5000, 9001):  # 9001 cuts in the middle of a day
        np.testing.assert_array_equal(full[:k], fn(long_df.iloc[:k].copy()))


def test_uptrend_uses_only_closed_days(long_df):
    a = uptrend(long_df)
    day = long_df["ts"].to_numpy() // 86400
    for d in np.unique(day)[300:320]:
        assert len(set(a[day == d])) == 1  # one value per day, fixed when the day starts


def test_uptrend_false_during_warmup(long_df):
    assert not uptrend(long_df)[:24 * 150].any()


def test_vol_stake_is_bounded(long_df):
    s = vol_target_stake(long_df)
    assert (s > 0).all() and (s <= 0.95).all()


def test_stake_is_fixed_at_signal_time():
    cfg = ExecConfig(fee=0, slippage=0, stake_pct=0.95)
    st = SimState(usdt=100.0)
    on_candle(st, cfg, 0, 10, 10, 10, 10, True, False, stake=0.5)
    on_candle(st, cfg, 60, 10, 10, 10, 10, False, False, stake=0.9)  # later value must not apply
    assert st.position.qty * st.position.entry_price == pytest.approx(50.0)
    assert st.usdt == pytest.approx(50.0)


def test_default_stake_unchanged_without_override():
    cfg = ExecConfig(fee=0, slippage=0, stake_pct=0.8)
    st = SimState(usdt=100.0)
    on_candle(st, cfg, 0, 10, 10, 10, 10, True, False)
    on_candle(st, cfg, 60, 10, 10, 10, 10, False, False)
    assert st.position.qty * st.position.entry_price == pytest.approx(80.0)


def test_smaller_stake_scales_risk(long_df):
    n = len(long_df)
    e, x = np.zeros(n, bool), np.zeros(n, bool)
    e[100] = True
    x[3000] = True
    cfg = ExecConfig(stake_pct=1.0)
    full = run_on_signals(long_df, e, x, "1h", 100.0, cfg).metrics
    half = run_on_signals(long_df, e, x, "1h", 100.0, cfg, stake=np.full(n, 0.5)).metrics
    assert abs(half["max_drawdown"]) < abs(full["max_drawdown"])


def test_folds_are_ordered_and_tests_never_overlap():
    ts = np.arange(0, 86400 * 1000, 3600)
    f = folds(ts, 0, 200, 100)
    assert len(f) >= 3
    for (a0, b0, c0), (a1, b1, c1) in zip(f, f[1:]):
        assert b0 - a0 == 200 * 86400 and c0 == b1
    assert all(tr < te < end for tr, te, end in f)


def test_walk_forward_is_deterministic_and_only_reports_test_windows(long_df):
    st = get_strategy("ema_crossover")
    start = int(long_df["ts"].iloc[24 * 210])
    a = walk_forward(st, long_df, "1h", start, train_days=120, test_days=40, trials=3)
    b = walk_forward(st, long_df, "1h", start, train_days=120, test_days=40, trials=3)
    assert a["metrics"] == b["metrics"]
    assert a["equity"][0][0] >= a["folds"][0]["test_start"]
    assert [e[0] for e in a["equity"]] == sorted({e[0] for e in a["equity"]})  # no window repeats


def test_walk_forward_test_window_ignores_later_candles(long_df):
    st = get_strategy("ema_crossover")
    start = int(long_df["ts"].iloc[24 * 210])
    full = walk_forward(st, long_df, "1h", start, train_days=120, test_days=40, trials=3)
    first_end = full["folds"][1]["test_start"]
    cut = long_df[long_df["ts"] < first_end + 86400 * 40].copy()
    short = walk_forward(st, cut, "1h", start, train_days=120, test_days=40, trials=3)
    assert short["folds"][0] == full["folds"][0]
