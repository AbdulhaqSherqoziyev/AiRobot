"""Parameter sweeps with chronological splits. The engine for a sweep is replaceable (VectorBT
or the native loop); the final candidate is always re-run on the authoritative native engine.

Discipline enforced here:
- signals are computed once over the whole series from causal indicators, then cut into segments;
- train, validation and test never overlap, and each segment starts flat;
- parameters are chosen on train and validation only, and walk-forward stays inside them;
- the test segment is run only for the single chosen set, so it cannot influence the choice;
- every parameter set is returned, not only the winner.
"""

from __future__ import annotations

import itertools
import platform
import statistics
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

import quantlab
from quantlab.backtest.core import ExecConfig, Filters
from quantlab.backtest.engine import run_on_signals
from quantlab.config import TIMEFRAMES
from quantlab.market.store import CandleStore
from quantlab.research import robustness, vbt_adapter
from quantlab.strategies.base import Strategy

# Measured on 3 pairs of 4h data, 96 sets: native 13.2 s and 194 MB, VectorBT 6.1 s and 1.1 GB; 576
# VectorBT sets took 3.7 GB. Native is the sensible choice on a memory-limited server.
MAX_COMBOS = {"vectorbt": 3000, "native": 1000}
METRICS = ("total_return", "net_profit", "total_trades", "profit_factor", "max_drawdown", "sharpe", "sortino", "win_rate", "exposure", "fees_paid")
MIN_TRADES_FOR_RATIOS = 10

# Thresholds a candidate has to meet before it may even enter a paper session. Meeting them is
# not evidence of profit: live trading stays behind the 30-day report and the owner's approval.
GATES = {
    "min_test_trades": 20, "min_test_return": 0.0, "min_profit_factor": 1.1, "max_drawdown": 25.0,
    "min_wf_positive_share": 0.6, "min_stability": 0.5, "min_pair_positive_share": 0.5, "max_engine_gap_pct": 3.0, "min_regimes": 2,
}


@dataclass(frozen=True)
class SweepConfig:
    fee: float = 0.001
    slippage: float = 0.0005
    stake_pct: float = 0.95
    stoploss_pct: float = 0.0
    takeprofit_pct: float = 0.0
    initial: float = 100.0
    train: float = 0.6
    validation: float = 0.2
    folds: int = 4
    min_trades: int = 5
    backend: str = "vectorbt"

    def __post_init__(self):
        if self.backend not in MAX_COMBOS:
            raise ValueError(f"noma'lum backend: {self.backend}")
        if not (0 < self.train and 0 < self.validation and self.train + self.validation < 1):
            raise ValueError("train + validation 1 dan kichik bo'lishi kerak")

    def exec_config(self, filters: Filters | None = None) -> ExecConfig:
        return ExecConfig(fee=self.fee, slippage=self.slippage, stake_pct=self.stake_pct, stoploss_pct=self.stoploss_pct, takeprofit_pct=self.takeprofit_pct, filters=filters or Filters())


def expand_grid(strategy: Strategy, grid: dict[str, list]) -> list[dict]:
    """All parameter sets, validated against the strategy's own bounds."""
    unknown = set(grid) - set(strategy.params)
    if unknown:
        raise ValueError(f"{strategy.key}: noma'lum parametrlar: {sorted(unknown)}")
    keys = sorted(grid)
    out = []
    for values in itertools.product(*(grid[k] for k in keys)):
        p = dict(zip(keys, values))
        strategy.resolve(p)
        if "ema_fast" in p and "ema_slow" in p and p["ema_fast"] >= p["ema_slow"]:
            continue
        out.append(p)
    return out or [{}]


def split_indices(n: int, first: int, train: float, validation: float) -> dict[str, tuple[int, int]]:
    """Consecutive half-open ranges over rows `first`..`n`."""
    span = n - first
    a = first + int(span * train)
    b = a + int(span * validation)
    return {"train": (first, a), "validation": (a, b), "test": (b, n)}


def wf_windows(start: int, end: int, folds: int) -> list[tuple[int, int, int]]:
    """Expanding in-sample, then the next window out of sample: (is_start, oos_start, oos_end)."""
    step = (end - start) // (folds + 2)
    if step <= 0:
        return []
    return [(start, start + step * (k + 2), start + step * (k + 3) if k < folds - 1 else end) for k in range(folds)]


def signal_matrices(strategy: Strategy, df: pd.DataFrame, combos: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    entries = np.zeros((len(df), len(combos)), dtype=bool)
    exits = np.zeros_like(entries)
    for j, p in enumerate(combos):
        sig = strategy.signals(df, p)
        entries[:, j], exits[:, j] = sig["enter"].to_numpy(), sig["exit"].to_numpy()
    return entries, exits


def simulate_native(df: pd.DataFrame, entries: np.ndarray, exits: np.ndarray, tf: str, cfg: ExecConfig, initial: float) -> list[dict]:
    return [run_on_signals(df, entries[:, j], exits[:, j], tf, initial, cfg).metrics for j in range(entries.shape[1])]


def _simulate(backend: str, df, entries, exits, tf, cfg, initial) -> list[dict]:
    if backend == "vectorbt":
        return vbt_adapter.simulate(df, entries, exits, tf, cfg, initial)
    return simulate_native(df, entries, exits, tf, cfg, initial)


def slim(m: dict) -> dict:
    out = {k: m.get(k) for k in METRICS}
    # A Sharpe from a handful of trades is noise, so it is not reported at all.
    if (m.get("total_trades") or 0) < MIN_TRADES_FOR_RATIOS:
        out["sharpe"] = out["sortino"] = None
    return out


def _median(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(statistics.median(vals), 6) if vals else None


def pool(per_pair: dict[str, dict]) -> dict:
    rows = list(per_pair.values())
    return {k: _median(rows, k) for k in METRICS}


def buy_hold_return(df: pd.DataFrame, a: int, b: int) -> float:
    return round((float(df["close"].iloc[b - 1]) / float(df["open"].iloc[a]) - 1) * 100, 4)


def regime(ret: float) -> str:
    return "bull" if ret > 10 else "bear" if ret < -10 else "range"


def _pick(rows: list[dict], cfg: SweepConfig) -> int | None:
    """Best by median validation Sharpe among sets with enough trades on both parts. Return is
    deliberately not the criterion: it favours whatever carried the most risk."""
    best, best_score = None, None
    for i, r in enumerate(rows):
        s = r["validation"]["sharpe"]
        if s is None or (r["train"]["total_trades"] or 0) < cfg.min_trades or (r["validation"]["total_trades"] or 0) < cfg.min_trades:
            continue
        if best_score is None or s > best_score:
            best, best_score = i, s
    return best


def eligibility(res: dict, gates: dict = GATES) -> dict:
    """Paper-candidate gate. `live` is never granted here."""
    c: list[dict] = []
    t = res.get("test_pooled") or {}

    def check(name: str, value, ok: bool, need) -> None:
        c.append({"name": name, "value": value, "need": need, "ok": bool(ok)})

    trades = sum((res.get("test_trades_by_pair") or {}).values())
    check("Test savdolari soni", trades, trades >= gates["min_test_trades"], f">= {gates['min_test_trades']}")
    r = t.get("total_return")
    check("Test sof daromadi (median)", r, r is not None and r > gates["min_test_return"], f"> {gates['min_test_return']}%")
    pf = t.get("profit_factor")
    check("Test profit factor", pf, pf is not None and pf >= gates["min_profit_factor"], f">= {gates['min_profit_factor']}")
    dd = t.get("max_drawdown")
    check("Test pasayishi", dd, dd is not None and abs(dd) <= gates["max_drawdown"], f"<= {gates['max_drawdown']}%")
    wf = (res.get("walk_forward") or {}).get("positive_share")
    check("Walk-forward musbat oynalar", wf, wf is not None and wf >= gates["min_wf_positive_share"], f">= {gates['min_wf_positive_share']:.0%}")
    st = (res.get("sensitivity") or {}).get("stability")
    check("Parametr barqarorligi", st, st is None or st >= gates["min_stability"], f">= {gates['min_stability']:.0%} (grid 1 nuqta bo'lsa o'tkaziladi)")
    pp = res.get("pair_positive_share")
    check("Juftliklar bo'yicha barqarorlik", pp, pp is not None and pp >= gates["min_pair_positive_share"], f">= {gates['min_pair_positive_share']:.0%}")
    gap = res.get("engine_gap_max_pct")
    check("Dvigatellar farqi", gap, gap is not None and gap <= gates["max_engine_gap_pct"], f"<= {gates['max_engine_gap_pct']} foiz punkt")
    regimes = res.get("regimes_covered") or []
    check("Bozor rejimlari qamrovi", ", ".join(regimes) or None, len(regimes) >= gates["min_regimes"], f">= {gates['min_regimes']} xil rejim (bull/bear/range)")
    ok = all(x["ok"] for x in c) and res.get("selected") is not None
    return {
        "status": "paper_candidate" if ok else "rejected", "checks": c,
        "live": "qulflangan: 30 kunlik hisobot va egasining tasdig'i kerak",
        "note": "Mezonlardan o'tish foyda isboti emas, faqat paper sinovga kirish sharti.",
    }


def run_sweep(frames: dict[str, pd.DataFrame], strategy: Strategy, grid: dict[str, list], timeframe: str, start_ts: int, cfg: SweepConfig, filters: dict[str, Filters] | None = None, on_progress: Callable[[float, str], None] | None = None, seed: int = 7) -> dict:
    """`frames` hold warm-up candles before `start_ts`; those never trade."""
    started = time.monotonic()
    tick = on_progress or (lambda *_: None)
    combos = expand_grid(strategy, grid)
    if len(combos) > MAX_COMBOS[cfg.backend]:
        raise ValueError(f"{len(combos)} ta kombinatsiya: {cfg.backend} uchun chegara {MAX_COMBOS[cfg.backend]}")
    if cfg.backend == "vectorbt" and not vbt_adapter.available():
        raise RuntimeError("vectorbt o'rnatilmagan: quantlab/requirements-research.txt yoki backend=native")
    filters = filters or {}
    per_pair: dict[str, dict] = {}
    for n_pair, (pair, df) in enumerate(frames.items()):
        first = int(np.searchsorted(df["ts"].to_numpy(), start_ts))
        if len(df) - first < 200:
            raise ValueError(f"{pair}: tanlangan davrda {len(df) - first} sham, kamida 200 kerak")
        tick(0.05 + 0.5 * n_pair / len(frames), f"{pair}: signallar va train/validation")
        ec = cfg.exec_config(filters.get(pair))
        entries, exits = signal_matrices(strategy, df, combos)
        seg = split_indices(len(df), first, cfg.train, cfg.validation)
        by_seg = {}
        for name in ("train", "validation"):
            a, b = seg[name]
            by_seg[name] = _simulate(cfg.backend, df.iloc[a:b], entries[a:b], exits[a:b], timeframe, ec, cfg.initial)
        per_pair[pair] = {"df": df, "seg": seg, "entries": entries, "exits": exits, "ec": ec, "first": first, **by_seg}

    rows = []
    for j, p in enumerate(combos):
        train = {pair: slim(d["train"][j]) for pair, d in per_pair.items()}
        val = {pair: slim(d["validation"][j]) for pair, d in per_pair.items()}
        rows.append({"params": p, "train": pool(train), "validation": pool(val), "per_pair": {pair: {"train": train[pair], "validation": val[pair]} for pair in per_pair}})
    pick = _pick(rows, cfg)
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["validation"]["sharpe"] is None, -(rows[i]["validation"]["sharpe"] or 0)))
    for rank, i in enumerate(order, 1):
        rows[i]["rank"] = rank
        rows[i]["selected"] = i == pick

    summary: dict = {
        "n_combos": len(combos), "selected": rows[pick]["params"] if pick is not None else None,
        "selection_rule": f"median validation Sharpe; har qismda kamida {cfg.min_trades} savdo, Sharpe uchun esa {MIN_TRADES_FOR_RATIOS} savdo",
        "multiple_testing_note": f"{len(combos)} ta to'plam sinaldi: eng yaxshisi tasodifan ham yaxshi ko'rinishi mumkin, shuning uchun test alohida.",
        "segments": {pair: {k: {"start": int(d["df"]["ts"].iloc[a]), "end": int(d["df"]["ts"].iloc[b - 1]), "candles": b - a, "buy_hold": buy_hold_return(d["df"], a, b), "regime": regime(buy_hold_return(d["df"], a, b))} for k, (a, b) in d["seg"].items()} for pair, d in per_pair.items()},
    }
    tick(0.6, "walk-forward")
    summary["walk_forward"] = _walk_forward(per_pair, combos, timeframe, cfg)
    if pick is not None:
        tick(0.8, "tanlangan to'plamni yakuniy sinash")
        summary.update(_final_runs(per_pair, combos, pick, rows, grid, timeframe, cfg, seed))
    summary["regimes_covered"] = sorted({s["regime"] for segs in summary["segments"].values() for s in segs.values()})
    summary["eligibility"] = eligibility(summary)
    repro = {
        "quantlab_version": quantlab.__version__ if hasattr(quantlab, "__version__") else None, "python": platform.python_version(),
        "numpy": np.__version__, "pandas": pd.__version__, "vectorbt": vbt_adapter.available(), "backend": cfg.backend, "seed": seed,
        "data_hash": {pair: CandleStore.data_hash(d["df"]) for pair, d in per_pair.items()}, "rows": {pair: len(d["df"]) for pair, d in per_pair.items()},
    }
    return {"rows": rows, "summary": summary, "repro": repro, "runtime_s": round(time.monotonic() - started, 3)}


def _walk_forward(per_pair: dict, combos: list[dict], tf: str, cfg: SweepConfig) -> dict:
    """Stays inside train+validation: the test segment plays no part in it."""
    folds = []
    for pair, d in per_pair.items():
        df, en, ex, ec = d["df"], d["entries"], d["exits"], d["ec"]
        for k, (a, m, b) in enumerate(wf_windows(d["seg"]["train"][0], d["seg"]["validation"][1], cfg.folds)):
            ins = _simulate(cfg.backend, df.iloc[a:m], en[a:m], ex[a:m], tf, ec, cfg.initial)
            scored = [(i, x) for i, x in enumerate(ins) if (x.get("total_trades") or 0) >= cfg.min_trades and x.get("sharpe") is not None]
            if not scored:
                folds.append({"pair": pair, "fold": k, "params": None, "oos_return": None, "oos_trades": 0, "buy_hold": buy_hold_return(df, m, b)})
                continue
            j = max(scored, key=lambda t: t[1]["sharpe"])[0]
            oos = _simulate(cfg.backend, df.iloc[m:b], en[m:b][:, [j]], ex[m:b][:, [j]], tf, ec, cfg.initial)[0]
            folds.append({"pair": pair, "fold": k, "params": combos[j], "oos_return": oos["total_return"], "oos_trades": oos["total_trades"], "oos_dd": oos["max_drawdown"], "buy_hold": buy_hold_return(df, m, b)})
    rets = [f["oos_return"] for f in folds if f["oos_return"] is not None]
    return {
        "folds": folds, "scored": len(rets), "total": len(folds), "positive_share": round(sum(r > 0 for r in rets) / len(folds), 4) if folds else None,
        "median_oos_return": round(statistics.median(rets), 4) if rets else None,
    }


def _downsample(eq: list[tuple[int, float]], n: int = 400) -> list[list[float]]:
    step = max(1, len(eq) // n)
    return [[t, round(e, 4)] for t, e in eq[::step]]


def _final_runs(per_pair: dict, combos: list[dict], pick: int, rows: list[dict], grid: dict, tf: str, cfg: SweepConfig, seed: int) -> dict:
    test, auth, gaps, curves, trades_pct, comparison = {}, {}, [], {}, [], []
    for pair, d in per_pair.items():
        df, ec = d["df"], d["ec"]
        a, b = d["seg"]["test"]
        en, ex = d["entries"][:, pick], d["exits"][:, pick]
        tested = _simulate(cfg.backend, df.iloc[a:b], en[a:b][:, None], ex[a:b][:, None], tf, ec, cfg.initial)[0]
        native = run_on_signals(df.iloc[a:b], en[a:b], ex[a:b], tf, cfg.initial, ec)
        test[pair], auth[pair] = slim(tested), slim(native.metrics)
        gap = abs((tested["total_return"] or 0) - (native.metrics["total_return"] or 0))
        gaps.append(gap)
        comparison.append({"pair": pair, "segment": "test", "backend": cfg.backend, "backend_return": tested["total_return"], "authoritative_return": native.metrics["total_return"], "backend_trades": tested["total_trades"], "authoritative_trades": native.metrics["total_trades"], "gap_pct_points": round(gap, 4), "rejected_orders": len(native.rejected)})
        curves[pair] = _downsample(native.equity)
        trades_pct += [t["pnl_pct"] for t in native.trades]
    by_params = {robustness.params_key(r["params"]): r for r in rows}
    returns = [m["total_return"] for m in auth.values() if m["total_return"] is not None]
    return {
        "test_by_pair": auth, "test_backend_by_pair": test, "test_pooled": pool(auth),
        "test_trades_by_pair": {p: m["total_trades"] for p, m in auth.items()},
        "pair_positive_share": round(sum(r > 0 for r in returns) / len(auth), 4) if auth else None,
        "engine_comparison": comparison, "engine_gap_max_pct": round(max(gaps), 4) if gaps else None, "equity_test": curves,
        "monte_carlo": robustness.monte_carlo_trades(trades_pct, seed=seed),
        "sensitivity": robustness.sensitivity(combos[pick], by_params, grid, lambda r: r["validation"]["total_return"]),
    }


PRESETS = {
    "rsi_ema_example": {
        "strategy": "rsi_ema_trend", "label": "RSI + EMA misol (spetsifikatsiyadagi 576 to'plam)",
        "grid": {"rsi_period": [7, 14, 21, 28], "rsi_entry": [20, 25, 30, 35], "rsi_exit": [65, 70, 75, 80], "ema_fast": [5, 10, 20], "ema_slow": [30, 50, 100]},
    },
    "jesse_ema_cross": {"strategy": "jesse_ema_cross", "label": "Jesse EMA Cross (parametrsiz)", "grid": {}},
    "jesse_rsi_trend": {"strategy": "jesse_rsi_trend", "label": "Jesse RSI Trend (parametrsiz)", "grid": {}},
}
