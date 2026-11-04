"""Historical backtest over one pair. Deterministic: same inputs give the same result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from quantlab.backtest.core import ExecConfig, Filters, SimState, on_candle
from quantlab.backtest.metrics import compute, monthly_returns
from quantlab.config import TIMEFRAMES
from quantlab.strategies.base import Strategy


@dataclass
class BacktestOutput:
    metrics: dict
    trades: list[dict]
    equity: list[tuple[int, float]]
    monthly: list[dict]
    rejected: list[str]


def exec_config(params: dict) -> ExecConfig:
    return ExecConfig(
        fee=float(params.get("fee", 0.001)),
        slippage=float(params.get("slippage", 0.0005)),
        stake_pct=float(params.get("stake_pct", 1.0)),
        stoploss_pct=float(params.get("stoploss_pct", 0.0)),
        takeprofit_pct=float(params.get("takeprofit_pct", 0.0)),
        filters=Filters(float(params.get("min_notional", 5.0)), float(params.get("step_size", 0.0)), float(params.get("min_qty", 0.0))),
    )


def run_on_signals(df: pd.DataFrame, enter, exit_, timeframe: str, initial: float, cfg: ExecConfig, on_progress: Callable[[float], None] | None = None, start_ts: int | None = None) -> BacktestOutput:
    state = SimState(usdt=initial)
    trades: list[dict] = []
    equity: list[tuple[int, float]] = []
    open_buy = None
    n = len(df)
    ts_a, o_a, h_a, l_a, c_a = (df[c].to_numpy() for c in ("ts", "open", "high", "low", "close"))
    for i in range(n):
        ts = int(ts_a[i])
        if start_ts is not None and ts < start_ts:
            continue  # warm-up candles feed the indicators but never trade
        fills = on_candle(state, cfg, ts, float(o_a[i]), float(h_a[i]), float(l_a[i]), float(c_a[i]), bool(enter[i]), bool(exit_[i]))
        for f in fills:
            if f.side == "buy":
                open_buy = f
            else:
                trades.append({
                    "entry_ts": open_buy.ts, "exit_ts": f.ts, "entry_price": open_buy.price, "exit_price": f.price, "qty": f.qty,
                    "fees": open_buy.fee + f.fee, "pnl": f.pnl, "pnl_pct": f.pnl_pct, "reason": f.reason,
                })
        equity.append((ts, state.equity(float(c_a[i]))))
        if on_progress and i % 500 == 0:
            on_progress(i / n)
    return BacktestOutput(compute(equity, trades, initial, TIMEFRAMES[timeframe]), trades, equity, monthly_returns(equity), state.rejected)


def run_backtest(strategy: Strategy, df: pd.DataFrame, params: dict, timeframe: str, initial: float = 100.0, cfg: ExecConfig | None = None, start_ts: int | None = None, on_progress=None) -> BacktestOutput:
    sig = strategy.signals(df, params)
    return run_on_signals(df, sig["enter"].to_numpy(), sig["exit"].to_numpy(), timeframe, initial, cfg or exec_config(params), on_progress, start_ts)
