"""The ten technical strategies. Spot, long only: `exit` closes the position, never shorts."""

from __future__ import annotations

import pandas as pd

from quantlab.strategies import indicators as ind
from quantlab.strategies.base import Param, RiskDefaults, Strategy


def cross_up(a: pd.Series, b) -> pd.Series:
    prev_b = b.shift() if isinstance(b, pd.Series) else b
    return (a > b) & (a.shift() <= prev_b)


def cross_down(a: pd.Series, b) -> pd.Series:
    prev_b = b.shift() if isinstance(b, pd.Series) else b
    return (a < b) & (a.shift() >= prev_b)


class RsiReversal(Strategy):
    """Enter when RSI recovers above the oversold level; exit when it reaches overbought."""
    key, name, color = "rsi_reversal", "RSI Reversal", "#3B82F6"
    description, indicators = "Mean reversion on RSI recovery from oversold.", ("rsi",)
    params = {"period": Param(14, 5, 40), "oversold": Param(30, 10, 45), "overbought": Param(70, 55, 90)}

    def compute(self, df, p):
        r = ind.rsi(df["close"], p["period"])
        return cross_up(r, p["oversold"]), r >= p["overbought"]


class EmaCrossover(Strategy):
    """Enter on fast EMA crossing above slow EMA; exit on the opposite cross."""
    key, name, color = "ema_crossover", "EMA Crossover", "#16B5CA"
    description, indicators = "Classic trend following on two EMAs.", ("ema",)
    params = {"fast": Param(12, 3, 50), "slow": Param(26, 10, 200)}

    def compute(self, df, p):
        f, s = ind.ema(df["close"], p["fast"]), ind.ema(df["close"], p["slow"])
        return cross_up(f, s), cross_down(f, s)


class MacdMomentum(Strategy):
    """Enter on MACD crossing above its signal line below zero-trend filter; exit on cross down."""
    key, name, color = "macd_momentum", "MACD Momentum", "#9747FF"
    description, indicators = "Momentum via MACD/signal crosses with an EMA trend filter.", ("macd", "ema")
    params = {"fast": Param(12, 5, 30), "slow": Param(26, 15, 60), "signal": Param(9, 3, 20), "trend": Param(100, 20, 300)}

    def compute(self, df, p):
        m, s, _ = ind.macd(df["close"], p["fast"], p["slow"], p["signal"])
        return cross_up(m, s) & (df["close"] > ind.ema(df["close"], p["trend"])), cross_down(m, s)


class BollingerBands(Strategy):
    """Enter when price closes back inside after piercing the lower band; exit at the middle band."""
    key, name, color = "bollinger_bands", "Bollinger Bands", "#EC4899"
    description, indicators = "Mean reversion from the lower band to the mean.", ("bollinger",)
    params = {"period": Param(20, 10, 60), "k": Param(2.0, 1.0, 3.5, 0.1, False)}

    def compute(self, df, p):
        lo, mid, _ = ind.bollinger(df["close"], p["period"], p["k"])
        return cross_up(df["close"], lo), df["close"] >= mid


class StochRsi(Strategy):
    """Enter on %K crossing above %D in the oversold zone; exit when %K crosses down overbought."""
    key, name, color = "stoch_rsi", "Stochastic RSI", "#FFA841"
    description, indicators = "Oscillator timing on the stochastic of RSI.", ("stoch_rsi",)
    params = {"period": Param(14, 5, 30), "smooth": Param(3, 2, 10), "low": Param(20, 5, 40), "high": Param(80, 60, 95)}

    def compute(self, df, p):
        k, d = ind.stoch_rsi(df["close"], p["period"], p["smooth"], p["smooth"])
        return cross_up(k, d) & (k < p["low"]), cross_down(k, d) & (k > p["high"])


class Supertrend(Strategy):
    """Enter when Supertrend flips up; exit when it flips down."""
    key, name, color = "supertrend", "Supertrend", "#16C784"
    description, indicators = "ATR-band trend flip.", ("supertrend", "atr")
    params = {"period": Param(10, 5, 40), "mult": Param(3.0, 1.0, 6.0, 0.1, False)}

    def compute(self, df, p):
        t = ind.supertrend(df, p["period"], p["mult"])
        return t & ~t.shift(fill_value=False), ~t & t.shift(fill_value=False)


class VwapReversion(Strategy):
    """Enter when price recovers above rolling VWAP from a discount; exit at a premium to VWAP."""
    key, name, color = "vwap", "VWAP Reversion", "#60A5FA"
    description, indicators = "Rolling VWAP discount/premium.", ("vwap",)
    params = {"window": Param(48, 12, 200), "discount": Param(1.0, 0.1, 5.0, 0.1, False), "premium": Param(1.0, 0.1, 5.0, 0.1, False)}

    def compute(self, df, p):
        v = ind.rolling_vwap(df, p["window"])
        dev = (df["close"] / v - 1) * 100
        return cross_up(dev, -p["discount"]), dev >= p["premium"]


class AdxTrend(Strategy):
    """Enter when ADX shows a strong trend and +DI crosses above -DI; exit when -DI crosses above."""
    key, name, color = "adx_trend", "ADX Trend", "#F0B90B"
    description, indicators = "Directional movement trend following.", ("adx",)
    params = {"period": Param(14, 5, 40), "threshold": Param(22, 10, 50)}

    def compute(self, df, p):
        a, pdi, mdi = ind.adx(df, p["period"])
        return cross_up(pdi, mdi) & (a > p["threshold"]), cross_down(pdi, mdi)


class AtrBreakout(Strategy):
    """Enter when the close breaks the prior close by a multiple of ATR; exit on a trailing ATR break."""
    key, name, color = "atr_breakout", "ATR Volatility", "#EA3943"
    description, indicators = "Volatility expansion breakout with an ATR trailing exit.", ("atr",)
    params = {"period": Param(14, 5, 50), "entry_mult": Param(1.5, 0.5, 4.0, 0.1, False), "exit_mult": Param(2.5, 0.5, 6.0, 0.1, False), "lookback": Param(20, 5, 100)}

    def compute(self, df, p):
        a = ind.atr(df, p["period"])
        c = df["close"]
        return c > c.shift() + p["entry_mult"] * a, c < c.rolling(p["lookback"], min_periods=p["lookback"]).max() - p["exit_mult"] * a


class MultiIndicator(Strategy):
    """Enter when trend (EMA), momentum (MACD histogram) and RSI range agree; exit when two of three fail."""
    key, name, color = "multi_indicator", "Multi-Indicator", "#FF7A45"
    description, indicators = "Confluence of trend, momentum and RSI.", ("ema", "macd", "rsi")
    params = {"fast": Param(20, 5, 60), "slow": Param(50, 20, 200), "rsi_low": Param(45, 20, 60), "rsi_high": Param(70, 55, 90)}
    risk = RiskDefaults(stoploss_pct=0.025)

    def compute(self, df, p):
        c = df["close"]
        trend = ind.ema(c, p["fast"]) > ind.ema(c, p["slow"])
        _, _, hist = ind.macd(c)
        mom = hist > 0
        r = ind.rsi(c)
        okr = (r > p["rsi_low"]) & (r < p["rsi_high"])
        ok = trend & mom & okr
        bad = (~trend).astype(int) + (~mom).astype(int) + (r >= p["rsi_high"]).astype(int)
        return ok & ~ok.shift(fill_value=False), bad >= 2
