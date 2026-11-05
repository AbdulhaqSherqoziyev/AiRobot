"""Robustness checks on a finished result. They describe uncertainty; they cannot prove an edge."""

from __future__ import annotations

import numpy as np


def monte_carlo_trades(trade_returns_pct: list[float], sims: int = 1000, seed: int = 7) -> dict:
    """Bootstrap of the closed trades: how much of the result depends on these exact trades and
    their order. Same idea as Jesse's monte_carlo_trades, written against this project's metrics."""
    r = np.asarray(trade_returns_pct, dtype=float) / 100
    if len(r) < 5:
        return {"sims": 0, "trades": len(r), "note": "5 tadan kam savdo: baholab bo'lmaydi"}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(r), size=(sims, len(r)))
    eq = np.cumprod(1 + r[idx], axis=1)
    finals = (eq[:, -1] - 1) * 100
    peak = np.maximum.accumulate(np.concatenate([np.ones((sims, 1)), eq], axis=1), axis=1)[:, 1:]
    dd = ((eq / peak - 1) * 100).min(axis=1)
    q = lambda a, p: round(float(np.percentile(a, p)), 4)  # noqa: E731
    return {
        "sims": sims, "seed": seed, "trades": len(r),
        "return_p5": q(finals, 5), "return_p50": q(finals, 50), "return_p95": q(finals, 95),
        "max_dd_p5": q(dd, 5), "max_dd_p50": q(dd, 50),
        "prob_loss": round(float((finals <= 0).mean()), 4),
    }


def neighbors(params: dict, grid: dict[str, list]) -> list[dict]:
    """Parameter sets one grid step away from `params`."""
    out = []
    for k, values in grid.items():
        vals = list(values)
        if params.get(k) not in vals or len(vals) < 2:
            continue
        i = vals.index(params[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append({**params, k: vals[j]})
    return out


def sensitivity(selected: dict, by_params: dict[str, dict], grid: dict[str, list], metric_of) -> dict:
    """How the validation result behaves one step away from the chosen parameters. A lone peak
    among poor neighbours is the usual signature of overfitting."""
    vals = []
    for n in neighbors(selected, grid):
        row = by_params.get(params_key(n))
        if row is not None and (v := metric_of(row)) is not None:
            vals.append(v)
    own = metric_of(by_params[params_key(selected)])
    if not vals or own is None:
        return {"neighbors": len(vals), "stability": None, "own_return": own}
    return {
        "neighbors": len(vals), "own_return": round(own, 4), "neighbor_median_return": round(float(np.median(vals)), 4),
        "neighbor_worst_return": round(float(np.min(vals)), 4), "stability": round(float(np.mean([v > 0 for v in vals])), 4),
    }


def params_key(p: dict) -> str:
    return "|".join(f"{k}={p[k]}" for k in sorted(p))
