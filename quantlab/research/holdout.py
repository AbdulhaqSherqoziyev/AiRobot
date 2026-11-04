"""Single evaluation of the pre-registered candidates on the untouched final period."""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from quantlab.backtest.core import ExecConfig
from quantlab.backtest.engine import run_on_signals
from quantlab.backtest.metrics import compute
from quantlab.config import get_settings
from quantlab.market.store import CandleStore
from quantlab.research.compare import WARMUP_DAYS, buy_hold, trend_hold
from quantlab.research.filters import vol_target_stake
from quantlab.strategies.base import get_strategy

CANDIDATES = ["atr_breakout", "ema_crossover", "multi_indicator"]
TF = "4h"


def run_strategy(df, key, start, fee, slip):
    sig = get_strategy(key).signals(df, {})
    cfg = ExecConfig(fee=fee, slippage=slip, stake_pct=0.95, stoploss_pct=0.03)
    return run_on_signals(df, sig["enter"].to_numpy(), sig["exit"].to_numpy(), TF, 100.0, cfg, start_ts=start, stake=vol_target_stake(df))


def portfolio_metrics(outs: list) -> dict:
    """Equal capital per pair, kept separate; no rebalancing."""
    frame = pd.concat([pd.Series(dict(o.equity)) for o in outs], axis=1).sort_index().ffill().bfill()
    eq = frame.sum(axis=1) / len(outs)
    trades = [t for o in outs for t in o.trades]
    return compute(list(zip(eq.index.tolist(), eq.tolist())), trades, 100.0, 14400)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True)
    a = ap.parse_args()
    st = get_settings()
    store = CandleStore(st.data_dir)
    rows, ports = [], []
    for label, fee, slip in (("normal", 0.001, 0.0005), ("double_cost", 0.002, 0.001)):
        outs = {k: [] for k in CANDIDATES}
        for pair in st.watchlist:
            df = store.load(pair, TF, a.start - WARMUP_DAYS * 86400)
            for key in CANDIDATES:
                o = run_strategy(df, key, a.start, fee, slip)
                outs[key].append(o)
                rows.append({"costs": label, "strategy": key, "pair": pair, **{k: o.metrics[k] for k in ("total_return", "max_drawdown", "profit_factor", "sharpe", "total_trades", "fees_paid", "exposure")}})
            if label == "normal":
                for name, m in (("BUY_HOLD", buy_hold(df, TF, a.start)), ("TREND_HOLD", trend_hold(df, TF, a.start, "trend+vol"))):
                    rows.append({"costs": label, "strategy": name, "pair": pair, **{k: m[k] for k in ("total_return", "max_drawdown", "profit_factor", "sharpe", "total_trades", "fees_paid", "exposure")}})
        for key in CANDIDATES:
            m = portfolio_metrics(outs[key])
            ports.append({"costs": label, "strategy": key, **{k: m[k] for k in ("total_return", "max_drawdown", "profit_factor", "sharpe", "total_trades")}})
    res = pd.DataFrame(rows)
    out = st.data_dir / "research"
    res.to_csv(out / "holdout.csv", index=False)
    pd.DataFrame(ports).to_csv(out / "holdout_portfolio.csv", index=False)


if __name__ == "__main__":
    main()
