import numpy as np
import pandas as pd
import pytest

from quantlab.backtest.core import ExecConfig, Filters, SimState, on_candle
from quantlab.backtest.engine import exec_config, run_backtest
from quantlab.backtest.metrics import compute, max_streak, monthly_returns
from quantlab.market.store import clean
from quantlab.strategies.base import REGISTRY, all_strategies, get_strategy

TECH = ["rsi_reversal", "ema_crossover", "macd_momentum", "bollinger_bands", "stoch_rsi", "supertrend", "vwap", "adx_trend", "atr_breakout", "multi_indicator"]


def test_all_fifteen_registered():
    all_strategies()
    assert set(TECH) <= set(REGISTRY)
    assert {"ml_lightgbm", "ml_xgboost", "ml_random_forest", "ml_lstm", "ml_rl"} <= set(REGISTRY)


@pytest.mark.parametrize("key", TECH)
def test_no_lookahead(key, candles):
    """A signal at i must not change when later candles are removed."""
    s = get_strategy(key)
    full = s.signals(candles)
    for k in (400, 700, 1100):
        part = s.signals(candles.iloc[:k].copy())
        assert (full.iloc[:k].to_numpy() == part.to_numpy()).all(), f"{key} leaks at {k}"


@pytest.mark.parametrize("key", TECH)
def test_generates_trades_and_balances_stay_positive(key, candles):
    out = run_backtest(get_strategy(key), candles, {"stoploss_pct": 0.03, "stake_pct": 0.95}, "1h")
    assert out.metrics["total_trades"] > 0, key
    assert all(e > 0 for _, e in out.equity)


def test_rejects_param_outside_range():
    with pytest.raises(ValueError):
        get_strategy("rsi_reversal").resolve({"period": 500})


def test_signal_executes_at_next_open_with_fee_and_slippage():
    cfg = ExecConfig(fee=0.001, slippage=0.001, stake_pct=1.0)
    st = SimState(usdt=100.0)
    assert on_candle(st, cfg, 0, 10, 11, 9, 10, True, False) == []  # signal only, no fill
    assert st.position is None and st.pending == "enter"
    fills = on_candle(st, cfg, 3600, 12, 13, 11.9, 12.5, False, False)
    assert fills[0].side == "buy" and fills[0].price == pytest.approx(12 * 1.001)
    pos = st.position
    assert pos.qty * pos.entry_price + pos.entry_fee == pytest.approx(100.0)
    assert st.usdt == pytest.approx(0.0, abs=1e-9)
    on_candle(st, cfg, 7200, 12.5, 13, 12, 12.5, False, True)
    fills = on_candle(st, cfg, 10800, 13, 14, 12.5, 13, False, False)
    f = fills[0]
    assert f.side == "sell" and f.price == pytest.approx(13 * 0.999)
    proceeds = pos.qty * f.price
    assert st.usdt == pytest.approx(proceeds - proceeds * 0.001)
    assert f.pnl == pytest.approx(st.usdt - 100.0)


def test_no_entry_without_balance_or_below_minimum():
    cfg = ExecConfig(filters=Filters(min_notional=5.0))
    st = SimState(usdt=3.0)
    on_candle(st, cfg, 0, 10, 10, 10, 10, True, False)
    assert on_candle(st, cfg, 60, 10, 10, 10, 10, False, False) == []
    assert st.position is None and st.usdt == 3.0 and st.rejected


def test_qty_respects_step_size():
    cfg = ExecConfig(fee=0, slippage=0, filters=Filters(step_size=0.01))
    st = SimState(usdt=100.0)
    on_candle(st, cfg, 0, 33, 33, 33, 33, True, False)
    on_candle(st, cfg, 60, 33, 33, 33, 33, False, False)
    assert st.position.qty == pytest.approx(3.03)
    assert st.usdt > 0


def test_stop_beats_takeprofit_and_gap_fills_at_open():
    cfg = ExecConfig(fee=0, slippage=0, stoploss_pct=0.05, takeprofit_pct=0.05)
    st = SimState(usdt=100.0)
    on_candle(st, cfg, 0, 100, 100, 100, 100, True, False)
    fills = on_candle(st, cfg, 60, 100, 110, 90, 100, False, False)
    assert fills[-1].reason == "stoploss" and fills[-1].price == pytest.approx(95)
    st = SimState(usdt=100.0)
    on_candle(st, cfg, 0, 100, 100, 100, 100, True, False)
    on_candle(st, cfg, 60, 100, 101, 99, 100, False, False)
    fills = on_candle(st, cfg, 120, 80, 81, 79, 80, False, False)
    assert fills[-1].price == pytest.approx(80)  # not the unavailable 95


def test_deterministic(candles):
    s = get_strategy("ema_crossover")
    a, b = run_backtest(s, candles, {}, "1h"), run_backtest(s, candles, {}, "1h")
    assert a.metrics == b.metrics and a.trades == b.trades


def test_warmup_candles_do_not_trade(candles):
    start = int(candles["ts"].iloc[500])
    out = run_backtest(get_strategy("ema_crossover"), candles, {}, "1h", start_ts=start)
    assert out.equity[0][0] == start and all(t["entry_ts"] > start for t in out.trades)


def test_metrics_known_values():
    eq = [(0, 100.0), (3600, 110.0), (7200, 99.0), (10800, 108.9)]
    tr = [{"pnl": 10.0, "pnl_pct": 10.0, "fees": 0.1, "entry_ts": 0, "exit_ts": 3600}, {"pnl": -11.0, "pnl_pct": -10.0, "fees": 0.1, "entry_ts": 3600, "exit_ts": 7200}]
    m = compute(eq, tr, 100.0, 3600)
    assert m["net_profit"] == pytest.approx(8.9)
    assert m["max_drawdown"] == pytest.approx(-10.0)
    assert m["profit_factor"] == pytest.approx(10 / 11, rel=1e-3)
    assert m["win_rate"] == 50 and m["consecutive_wins"] == 1 and m["fees_paid"] == pytest.approx(0.2)
    assert max_streak([True, True, False, True]) == 2


def test_profit_factor_null_without_losses():
    assert compute([(0, 100.0), (60, 101.0)], [{"pnl": 1.0, "pnl_pct": 1.0, "fees": 0, "entry_ts": 0, "exit_ts": 60}], 100.0, 60)["profit_factor"] is None


def test_monthly_returns_compound_to_total():
    eq = [(1700000000 + i * 86400 * 10, 100 * 1.01 ** i) for i in range(10)]
    total = np.prod([1 + m["ret"] / 100 for m in monthly_returns(eq)])
    assert total == pytest.approx(1.01 ** 9, rel=1e-3)


def test_clean_removes_duplicates_bad_rows_and_finds_gaps():
    df = pd.DataFrame({"ts": [3600, 3600, 7200, 18000, 21600], "open": [1, 1, 1, 1, 1.0], "high": [2, 2, 2, 2, 0.5], "low": [0.5, 0.5, 0.5, 0.5, 0.4], "close": [1, 1, 1, 1, 1.0], "volume": [1, 1, 1, 1, 1.0]})
    out, rep = clean(df, "1h")
    assert rep.duplicates == 1 and rep.invalid == 1 and rep.gaps == [(10800, 14400)] and len(out) == 3


def test_exec_config_from_params():
    assert exec_config({"fee": 0.002, "stoploss_pct": 0.1}).fee == 0.002
