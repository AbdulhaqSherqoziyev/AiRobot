"""Optional VectorBT backend for exploratory sweeps. Never used for paper or live accounting.

VectorBT is licensed Apache 2.0 with the Commons Clause, so it is only imported when installed
(quantlab/requirements-research.txt) and enabled. It is mapped onto Quant Lab's assumptions:
- a signal at candle i fills at the open of i+1 (signals shifted by one, price=open);
- fee and slippage are percentages on both legs, long only, one position at a time;
- stake is a fraction of cash with the fee included, as in backtest.core._buy.
- an entry and exit on one candle resolve as in the engine: flat enters, in a position exits.

Lot-size rounding is deliberately not passed on: VectorBT's size_granularity floors the sell by
float division, leaves a dust position and silently blocks later entries (seen on real BTC data:
36 trades and -10.38% instead of 44 and -4.07%). Min notional is not modelled either. Remaining
differences are measured in tests_quantlab/test_vbt_parity.py, and the final candidate is always
re-run on the authoritative engine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantlab.backtest.core import ExecConfig
from quantlab.backtest.metrics import compute
from quantlab.config import TIMEFRAMES


def available() -> str | None:
    """Installed version, or None."""
    try:
        from importlib.metadata import version

        return version("vectorbt")
    except Exception:  # noqa: BLE001
        return None


def _shift(a: np.ndarray) -> np.ndarray:
    out = np.zeros_like(a)
    out[1:] = a[:-1]
    return out


def resolve_conflicts(entries: np.ndarray, exits: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Columns with a same-candle entry and exit get the engine's rule, which depends on whether a
    position is open. Exact without stops; with stops the position state is an approximation."""
    conflicted = np.flatnonzero((entries & exits).any(axis=0))
    if not len(conflicted):
        return entries, exits
    entries, exits = entries.copy(), exits.copy()
    for col in conflicted:
        in_pos = False
        for i in np.flatnonzero(entries[:, col] | exits[:, col]):
            enter, leave = entries[i, col] and not in_pos, exits[i, col] and in_pos
            entries[i, col], exits[i, col] = enter, leave
            in_pos = (in_pos or enter) and not leave
    return entries, exits


def simulate(df: pd.DataFrame, entries: np.ndarray, exits: np.ndarray, timeframe: str, cfg: ExecConfig, initial: float) -> list[dict]:
    """One metrics dict per column of the boolean matrices, using the shared metric functions."""
    import vectorbt as vbt

    n_cols = entries.shape[1]
    entries, exits = resolve_conflicts(entries, exits)
    kwargs = {}
    col = lambda name: df[name].to_numpy()[:, None]  # noqa: E731  (n, 1) broadcasts across the parameter columns
    if cfg.stoploss_pct > 0 or cfg.takeprofit_pct > 0:
        kwargs = {"open": col("open"), "high": col("high"), "low": col("low")}
        if cfg.stoploss_pct > 0:
            kwargs["sl_stop"] = cfg.stoploss_pct
        if cfg.takeprofit_pct > 0:
            kwargs["tp_stop"] = cfg.takeprofit_pct
    pf = vbt.Portfolio.from_signals(
        close=col("close"), entries=_shift(entries), exits=_shift(exits), price=col("open"),
        fees=cfg.fee, slippage=cfg.slippage, size=cfg.stake_pct, size_type="percent", init_cash=initial,
        direction="longonly", accumulate=False, freq=f"{TIMEFRAMES[timeframe]}s", **kwargs,
    )
    values = np.asarray(pf.value()).reshape(len(df), n_cols)
    rec = pf.trades.closed.records_arr
    ts = df["ts"].to_numpy()
    out = []
    for col in range(n_cols):
        r = rec[rec["col"] == col]
        trades = [{
            "entry_ts": int(ts[t["entry_idx"]]), "exit_ts": int(ts[t["exit_idx"]]), "entry_price": float(t["entry_price"]), "exit_price": float(t["exit_price"]),
            "qty": float(t["size"]), "fees": float(t["entry_fees"] + t["exit_fees"]), "pnl": float(t["pnl"]), "pnl_pct": float(t["return"]) * 100, "reason": "signal",
        } for t in r]
        out.append(compute(list(zip(ts.tolist(), values[:, col].tolist())), trades, initial, TIMEFRAMES[timeframe]))
    return out
