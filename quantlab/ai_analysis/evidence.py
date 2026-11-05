"""Builds the timestamped, numbers-only data pack an analyst may use. Only closed candles go in,
and no external text does, so nothing a model reads can carry instructions."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from quantlab.config import TIMEFRAMES
from quantlab.strategies import indicators as ind

SOURCE_CANDLES = "binance-spot-public:klines"
SOURCE_BOOK = "binance-spot-public:depth"


def _num(x) -> float | None:
    x = float(x)
    return None if np.isnan(x) or np.isinf(x) else round(x, 6)


def build_pack(df: pd.DataFrame, pair: str, timeframe: str, micro: dict | None = None, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    step = TIMEFRAMES[timeframe]
    closed = df[df["ts"] + step <= now]
    if len(closed) < 210:
        raise ValueError(f"{pair} {timeframe}: yopiq sham kam ({len(closed)}), kamida 210 kerak")
    c = closed["close"]
    last_ts = int(closed["ts"].iloc[-1])
    macd_line, macd_sig, _ = ind.macd(c)
    values = {
        "close": c.iloc[-1], "rsi_14": ind.rsi(c, 14).iloc[-1], "ema_20": ind.ema(c, 20).iloc[-1], "ema_50": ind.ema(c, 50).iloc[-1], "ema_200": ind.ema(c, 200).iloc[-1],
        "atr_14_pct": ind.atr(closed, 14).iloc[-1] / c.iloc[-1] * 100, "adx_14": ind.adx(closed, 14)[0].iloc[-1], "macd": macd_line.iloc[-1], "macd_signal": macd_sig.iloc[-1],
        "return_20_candles_pct": (c.iloc[-1] / c.iloc[-21] - 1) * 100, "return_100_candles_pct": (c.iloc[-1] / c.iloc[-101] - 1) * 100,
        "max_drawdown_100_candles_pct": (c.tail(100) / c.tail(100).cummax() - 1).min() * 100,
    }
    pack = {
        "symbol": pair, "timeframe": timeframe, "built_at": int(now), "last_closed_candle_ts": last_ts,
        "indicators": {k: {"value": _num(v), "timestamp": last_ts, "source": SOURCE_CANDLES} for k, v in values.items()},
        "recent_closes": [[int(t), _num(x)] for t, x in zip(closed["ts"].tail(30), c.tail(30))],
        "sources": [SOURCE_CANDLES], "timestamps": [last_ts] + [int(t) for t in closed["ts"].tail(30)],
        # Stated outright so an analyst has no reason to invent these.
        "unavailable": {"news": True, "sentiment": True, "fundamentals": True, "order_book": True},
    }
    if micro and micro.get("status") == "ok" and micro.get("metrics"):
        m, at = micro["metrics"], int(micro["as_of"])
        pack["order_book"] = {"timestamp": at, "source": SOURCE_BOOK, "spread_bps": _num(m["spread_bps"]), "depth": m["depth"]}
        pack["sources"].append(SOURCE_BOOK)
        pack["timestamps"].append(at)
        pack["unavailable"]["order_book"] = False
    return pack
