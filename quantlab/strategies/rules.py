"""Strategy from the visual builder: entry and exit conditions over named indicators.
Rules are data, never code, so an edit in the browser cannot execute anything."""

from __future__ import annotations

import pandas as pd

from quantlab.strategies import indicators as ind
from quantlab.strategies.base import Strategy
from quantlab.strategies.technical import cross_down, cross_up

OPS = {"lt", "gt", "le", "ge", "xa", "xb"}


def _series(df: pd.DataFrame, name: str, prm: dict) -> pd.Series:
    c = df["close"]
    g = lambda k, d: int(prm.get(k, d))  # noqa: E731
    table = {
        "close": lambda: c, "open": lambda: df["open"], "high": lambda: df["high"], "low": lambda: df["low"], "volume": lambda: df["volume"],
        "rsi": lambda: ind.rsi(c, g("rsiP", 14)), "emaF": lambda: ind.ema(c, g("emaF", 20)), "emaS": lambda: ind.ema(c, g("emaS", 50)), "ema200": lambda: ind.ema(c, 200), "sma50": lambda: ind.sma(c, 50),
        # The builder labels `macd` as the histogram and `atr` as a percentage of price.
        "macd": lambda: ind.macd(c, g("macdF", 12), g("macdS", 26), g("macdSig", 9))[2], "macdLine": lambda: ind.macd(c, g("macdF", 12), g("macdS", 26), g("macdSig", 9))[0], "macdSig": lambda: ind.macd(c, g("macdF", 12), g("macdS", 26), g("macdSig", 9))[1],
        "bbl": lambda: ind.bollinger(c, g("bbP", 20), float(prm.get("bbK", 2)))[0], "bbm": lambda: ind.bollinger(c, g("bbP", 20), float(prm.get("bbK", 2)))[1], "bbu": lambda: ind.bollinger(c, g("bbP", 20), float(prm.get("bbK", 2)))[2],
        "atr": lambda: ind.atr(df, 14) / c * 100, "adx": lambda: ind.adx(df, 14)[0], "vwap": lambda: ind.rolling_vwap(df, 48), "vol": lambda: df["volume"], "stoch": lambda: ind.stoch_rsi(c)[0],
    }
    if name not in table:
        raise ValueError(f"unknown indicator {name}")
    return table[name]()


def _condition(df: pd.DataFrame, r: dict, prm: dict, cache: dict) -> pd.Series:
    if r.get("op") not in OPS:
        raise ValueError(f"unknown operator {r.get('op')}")
    a = cache.get(r["ind"])
    if a is None:
        a = cache[r["ind"]] = _series(df, r["ind"], prm)
    if r.get("kind") == "ind":
        b = cache.get(r["val"])
        if b is None:
            b = cache[r["val"]] = _series(df, r["val"], prm)
    else:
        b = float(r["val"])
    op = r["op"]
    if op == "lt":
        return a < b
    if op == "gt":
        return a > b
    if op == "le":
        return a <= b
    if op == "ge":
        return a >= b
    return cross_up(a, b) if op == "xa" else cross_down(a, b)


def _combine(df: pd.DataFrame, rows: list[dict], join: str, prm: dict, cache: dict) -> pd.Series:
    if not rows:
        return pd.Series(False, index=df.index)
    out = None
    for r in rows:
        c = _condition(df, r, prm, cache).fillna(False)
        out = c if out is None else (out | c if join == "OR" else out & c)
    return out


class RuleBuilder(Strategy):
    """Enter and exit by the conditions set in the strategy builder."""
    key, name, color = "rule_builder", "Rule Builder", "#38BDF8"
    description = "Strategy assembled from indicator conditions in the visual builder."
    seedable = False

    def signals(self, df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        p = params or {}
        rules = p.get("rules") or {}
        cache: dict = {}
        prm = rules.get("prm") or {}
        join = rules.get("join") or {}
        enter = _combine(df, rules.get("entry") or [], join.get("entry", "AND"), prm, cache)
        exit_ = _combine(df, rules.get("exit") or [], join.get("exit", "OR"), prm, cache)
        return pd.DataFrame({"enter": enter.to_numpy(dtype=bool), "exit": exit_.to_numpy(dtype=bool)}, index=df.index)

    def compute(self, df, p):  # pragma: no cover - signals() is overridden
        raise NotImplementedError


def validate(rules: dict) -> None:
    """Rejects unknown indicators and operators before a version is saved."""
    import numpy as np

    n = 300
    c = pd.Series(100 + np.sin(np.arange(n) / 5) * 5)
    df = pd.DataFrame({"ts": np.arange(n) * 3600, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 10.0})
    if not rules.get("entry"):
        raise ValueError("kamida bitta kirish sharti kerak")
    RuleBuilder().signals(df, {"rules": rules})
