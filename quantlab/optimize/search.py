"""Optuna parameter search. The objective sees only the in-sample period; the best trials
are then re-run on an untouched out-of-sample period, which decides their eligibility."""

from __future__ import annotations

import math

import optuna
import pandas as pd

from quantlab.backtest.engine import run_backtest
from quantlab.strategies.base import Strategy

optuna.logging.set_verbosity(optuna.logging.WARNING)


def score(m: dict, objective: str = "composite", min_trades: int = 10, max_dd: float = 25.0) -> float:
    trades = m["total_trades"]
    if trades < min_trades or (m["max_drawdown"] or 0) < -max_dd:
        return -100.0 + trades * 0.01  # constraint violated, with a gradient toward more trades
    pf = m["profit_factor"] if m["profit_factor"] is not None else 1.0
    sharpe = m["sharpe"] or 0.0
    ret = m["total_return"] or 0.0
    if objective == "return":
        return ret
    if objective == "sharpe":
        return sharpe
    if objective == "profit_factor":
        return pf
    dd = abs(m["max_drawdown"] or 0.0)
    # Deliberately not maximum return: reward risk-adjusted, repeatable results.
    return sharpe + 0.5 * min(pf, 3.0) + ret / max(dd, 1.0) * 0.25 + 0.1 * math.log1p(trades)


def oos_passes(m: dict) -> bool:
    """Part of eligibility. A config must also be profitable in-sample: one that only made
    money on the unseen period got lucky there rather than showing a repeatable edge."""
    return (m["total_return"] or 0) > 0 and (m["profit_factor"] or 0) > 1.0 and m["total_trades"] >= 3


def optimize(strategy: Strategy, df: pd.DataFrame, timeframe: str, ranges: dict | None = None, trials: int = 50, oos_frac: float = 0.3, objective: str = "composite", initial: float = 100.0, fixed: dict | None = None, min_trades: int = 10, max_dd: float = 25.0, seed: int = 42, top_k: int = 5, progress=None, should_stop=None) -> dict:
    split = int(len(df) * (1 - oos_frac))
    if split < 300 or len(df) - split < 100:
        raise ValueError("not enough candles for an in-sample and out-of-sample split")
    train = df.iloc[:split].reset_index(drop=True)
    oos_start = int(df["ts"].iloc[split])
    fixed = fixed or {}
    ranges = ranges or {}

    def suggest(t: optuna.Trial) -> dict:
        out = {}
        for k, p in strategy.params.items():
            lo, hi = ranges.get(k, (p.low, p.high))
            out[k] = t.suggest_int(k, int(lo), int(hi)) if p.integer else t.suggest_float(k, float(lo), float(hi))
        return out

    def fn(t: optuna.Trial) -> float:
        if should_stop and should_stop():
            t.study.stop()
        m = run_backtest(strategy, train, {**fixed, **suggest(t)}, timeframe, initial).metrics
        t.set_user_attr("metrics", m)
        if progress:
            progress(t.number / trials)
        return score(m, objective, min_trades, max_dd)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(fn, n_trials=trials)
    done = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    top = []
    seen = set()
    for t in sorted(done, key=lambda t: -t.value):
        key = tuple(sorted(t.params.items()))
        if key in seen:
            continue
        seen.add(key)
        # The whole frame is passed so indicators are warm, but only OOS candles trade.
        oos = run_backtest(strategy, df, {**fixed, **t.params}, timeframe, initial, start_ts=oos_start).metrics
        top.append({"params": t.params, "score": round(t.value, 4), "in_sample": t.user_attrs["metrics"], "out_of_sample": oos, "eligible": oos_passes(oos) and (t.user_attrs["metrics"]["total_return"] or 0) > 0})
        if len(top) >= top_k:
            break
    return {"trials": len(done), "objective": objective, "oos_start": oos_start, "top": top, "history": [{"n": t.number, "value": round(t.value, 4), "params": t.params} for t in done][-400:]}
