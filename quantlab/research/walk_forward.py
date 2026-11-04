"""Rolling walk-forward: tune on a training window, trade the next window with those
parameters, roll forward. Only the stitched test windows count as a result."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantlab.backtest.core import ExecConfig
from quantlab.backtest.engine import run_on_signals
from quantlab.backtest.metrics import compute
from quantlab.config import TIMEFRAMES
from quantlab.optimize.search import score
from quantlab.research.filters import uptrend, vol_target_stake
from quantlab.strategies.base import Strategy

import optuna


def folds(ts: np.ndarray, start_ts: int, train_days: int, test_days: int) -> list[tuple[int, int, int]]:
    """(train_start, test_start, test_end) timestamps; test windows never overlap."""
    out = []
    t = start_ts + train_days * 86400
    end = int(ts[-1])
    while t + test_days * 86400 <= end + 86400:
        out.append((t - train_days * 86400, t, t + test_days * 86400))
        t += test_days * 86400
    return out


def _trade(st: Strategy, df, params, tf, start, end, trend, vol, stop, initial, up, stakes):
    # Signals see history up to the window end only, so nothing later can leak in.
    w = df[df["ts"] < end]
    sig = st.signals(w, params)
    e = sig["enter"].to_numpy()
    if trend:
        e = e & up[: len(w)]
    cfg = ExecConfig(fee=0.001, slippage=0.0005, stake_pct=0.95, stoploss_pct=stop)
    return run_on_signals(w, e, sig["exit"].to_numpy(), tf, initial, cfg, start_ts=start, stake=stakes[: len(w)] if vol else None)


def walk_forward(st: Strategy, df: pd.DataFrame, tf: str, start_ts: int, train_days: int = 720, test_days: int = 180, trials: int = 25, trend: bool = True, vol: bool = True, seed: int = 42, tune_stop: bool = True) -> dict:
    up, stakes = uptrend(df), vol_target_stake(df)
    equity: list[tuple[int, float]] = []
    trades: list[dict] = []
    capital, chosen = 100.0, []
    ts = df["ts"].to_numpy()
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    for tr_start, te_start, te_end in folds(ts, start_ts, train_days, test_days):
        def objective(t):
            p = {}
            for k, d in st.params.items():
                p[k] = t.suggest_int(k, int(d.low), int(d.high)) if d.integer else t.suggest_float(k, d.low, d.high)
            stop = t.suggest_float("stop", 0.02, 0.15) if tune_stop else 0.03
            try:
                m = _trade(st, df, p, tf, tr_start, te_start, trend, vol, stop, 100.0, up, stakes).metrics
            except ValueError:
                return -1000.0
            return score(m, "composite", min_trades=8, max_dd=35.0)

        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
        study.optimize(objective, n_trials=trials)
        best = dict(study.best_params)
        stop = best.pop("stop", 0.03)
        out = _trade(st, df, best, tf, te_start, te_end, trend, vol, stop, capital, up, stakes)
        # The window's open position is closed at its end by the stitching: equity is marked
        # to market, and the next window starts flat, slightly overstating trading activity.
        equity += out.equity
        trades += out.trades
        if out.equity:
            capital = out.equity[-1][1]
        chosen.append({"test_start": te_start, "params": {**best, "stop": round(stop, 4)}, "fold_return": out.metrics["total_return"], "train_score": round(study.best_value, 3)})
    m = compute(equity, trades, 100.0, TIMEFRAMES[tf]) if equity else None
    return {"metrics": m, "folds": chosen, "equity": equity}
