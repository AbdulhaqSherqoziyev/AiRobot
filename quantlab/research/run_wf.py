"""Does tuning beat default parameters? Both are scored on the same unseen test windows of the
development period. Holdout candles are never loaded here."""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from quantlab.config import get_settings
from quantlab.market.store import CandleStore
from quantlab.research.compare import WARMUP_DAYS, evaluate
from quantlab.research.walk_forward import folds, walk_forward
from quantlab.strategies.base import get_strategy

CANDIDATES = [("atr_breakout", "4h"), ("ema_crossover", "4h"), ("multi_indicator", "4h")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--dev-end", type=int, required=True)
    ap.add_argument("--trials", type=int, default=25)
    a = ap.parse_args()
    st = get_settings()
    store = CandleStore(st.data_dir)
    rows, detail = [], {}
    for key, tf in CANDIDATES:
        strat = get_strategy(key)
        for pair in st.watchlist:
            df = store.load(pair, tf, a.start - WARMUP_DAYS * 86400, a.dev_end)
            wf = walk_forward(strat, df, tf, a.start, trials=a.trials, trend=False, vol=True)
            first = wf["folds"][0]["test_start"]
            sig = strat.signals(df, {})
            base = evaluate(df, sig["enter"].to_numpy(), sig["exit"].to_numpy(), tf, first, "vol")
            m = wf["metrics"]
            rows.append({"strategy": key, "pair": pair, "wf_ret": m["total_return"], "default_ret": base["total_return"], "wf_dd": m["max_drawdown"], "default_dd": base["max_drawdown"], "wf_sharpe": m["sharpe"], "default_sharpe": base["sharpe"], "wf_trades": m["total_trades"], "default_trades": base["total_trades"], "folds": len(wf["folds"])})
            detail[f"{key}|{pair}"] = wf["folds"]
            print(key, pair, flush=True)
    res = pd.DataFrame(rows)
    out = st.data_dir / "research"
    res.to_csv(out / "walk_forward.csv", index=False)
    (out / "walk_forward_folds.json").write_text(json.dumps(detail, indent=1))


if __name__ == "__main__":
    main()
