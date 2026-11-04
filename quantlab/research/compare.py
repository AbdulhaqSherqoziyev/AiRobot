"""Grid comparison on the development period. Selection happens here. The final holdout
period is deliberately not loaded by this module: it is only for `holdout.py`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from quantlab.backtest.core import ExecConfig
from quantlab.backtest.engine import run_on_signals
from quantlab.config import TIMEFRAMES, get_settings
from quantlab.market.store import CandleStore
from quantlab.research.filters import uptrend, vol_target_stake
from quantlab.strategies.base import get_strategy

TECH = ["rsi_reversal", "ema_crossover", "macd_momentum", "bollinger_bands", "stoch_rsi", "supertrend", "vwap", "adx_trend", "atr_breakout", "multi_indicator"]
VARIANTS = {"base": (False, False), "trend": (True, False), "vol": (False, True), "trend+vol": (True, True)}
FEE, SLIP, STOP = 0.001, 0.0005, 0.03
WARMUP_DAYS = 260


def evaluate(df: pd.DataFrame, enter, exit_, tf: str, start_ts: int, variant: str, stop: float = STOP) -> dict:
    use_trend, use_vol = VARIANTS[variant]
    up = uptrend(df)
    e = np.asarray(enter) & up if use_trend else np.asarray(enter)
    stake = vol_target_stake(df) if use_vol else None
    cfg = ExecConfig(fee=FEE, slippage=SLIP, stake_pct=0.95, stoploss_pct=stop)
    return run_on_signals(df, e, np.asarray(exit_), tf, 100.0, cfg, start_ts=start_ts, stake=stake).metrics


def buy_hold(df: pd.DataFrame, tf: str, start_ts: int, stake=None) -> dict:
    """Same costs and engine: enter on the first candle and never leave."""
    enter = np.ones(len(df), dtype=bool)
    return run_on_signals(df, enter, np.zeros(len(df), dtype=bool), tf, 100.0, ExecConfig(fee=FEE, slippage=SLIP, stake_pct=0.999), start_ts=start_ts).metrics


def trend_hold(df: pd.DataFrame, tf: str, start_ts: int, variant: str) -> dict:
    """Baseline with no indicator strategy at all: long while the daily trend is up."""
    up = uptrend(df)
    return evaluate(df, up, ~up, tf, start_ts, variant, stop=0.0)


def run(data_dir: Path, pairs: list[str], start_ts: int, dev_end_ts: int, out: Path) -> pd.DataFrame:
    store = CandleStore(data_dir)
    rows = []
    for tf in ("1h", "4h", "1d"):
        for pair in pairs:
            # Loads only up to dev_end_ts: holdout candles cannot influence anything here.
            df = store.load(pair, tf, start_ts - WARMUP_DAYS * 86400, dev_end_ts)
            if (df["ts"] >= start_ts).sum() < 100:
                continue
            first = max(start_ts, int(df["ts"].iloc[0]) + WARMUP_DAYS * 86400)
            def add(name, variant, m):
                rows.append({"strategy": name, "tf": tf, "pair": pair, "variant": variant, **{k: m[k] for k in ("total_return", "max_drawdown", "profit_factor", "sharpe", "total_trades", "fees_paid", "exposure")}})
            add("BUY_HOLD", "-", buy_hold(df, tf, first))
            for v in VARIANTS:
                if VARIANTS[v][0]:
                    add("TREND_HOLD", v, trend_hold(df, tf, first, v))
            for key in TECH:
                st = get_strategy(key)
                sig = st.signals(df, {})
                for v in VARIANTS:
                    add(key, v, evaluate(df, sig["enter"].to_numpy(), sig["exit"].to_numpy(), tf, first, v))
            print(tf, pair, len(df), flush=True)
    res = pd.DataFrame(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(out, index=False)
    return res


def summarize(res: pd.DataFrame) -> pd.DataFrame:
    bh = res[res.strategy == "BUY_HOLD"].set_index(["tf", "pair"])
    res = res.join(bh[["total_return", "max_drawdown", "sharpe"]].add_prefix("bh_"), on=["tf", "pair"])
    g = res.groupby(["strategy", "tf", "variant"])
    out = pd.DataFrame({
        "pairs": g.size(), "med_return": g.total_return.median(), "med_dd": g.max_drawdown.median(), "worst_dd": g.max_drawdown.min(), "med_sharpe": g.sharpe.median(), "med_pf": g.profit_factor.median(),
        "med_trades": g.total_trades.median(), "med_fees": g.fees_paid.median(), "pos_share": g.total_return.apply(lambda s: (s > 0).mean() * 100),
        "beat_bh_sharpe": g.apply(lambda x: (x.sharpe > x.bh_sharpe).mean() * 100, include_groups=False),
    })
    return out.round(2).reset_index().sort_values("med_sharpe", ascending=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--dev-end", type=int, required=True)
    a = ap.parse_args()
    st = get_settings()
    out = st.data_dir / "research" / "dev_grid.csv"
    res = run(st.data_dir, list(st.watchlist), a.start, a.dev_end, out)
    s = summarize(res)
    s.to_csv(out.with_name("dev_summary.csv"), index=False)
    pd.set_option("display.width", 200, "display.max_rows", 200, "display.max_columns", 30)
    print(s.head(30).to_string(index=False))


if __name__ == "__main__":
    main()
