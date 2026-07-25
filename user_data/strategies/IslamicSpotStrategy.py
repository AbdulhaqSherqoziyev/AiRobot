"""
IslamicSpotStrategy — conservative, transparent, long-only spot strategy.

Design goals (per the platform constitution, `claudeSkills.MD`): capital
preservation first, fewer but safer trades, no gambling. This is a rule-based
trend-following strategy — every decision is explainable, there is no leverage,
no shorting, and it trades spot only.

Regime + pullback logic:
* Only trade when the market is in a confirmed uptrend (EMA50 > EMA200) and price
  is above the medium trend (EMA50).
* Enter on a momentum turn (RSI crossing up through its midline) rather than
  chasing strength, with a trend-strength (ADX) and volume confirmation.
* Exit on modest ROI targets, a hard stoploss, a trailing stop once in profit, or
  a trend break — whichever comes first.

Tune values in backtesting before any live use. Compliance/risk guards
(spot-only, pair screening, order gate, loss limits, circuit breaker) are enforced
by the platform independently of this strategy.
"""

from datetime import datetime  # noqa: F401  (available for callbacks)

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IStrategy


class IslamicSpotStrategy(IStrategy):
    INTERFACE_VERSION = 3

    # Spot, long only — no shorting (also enforced by the platform).
    can_short = False

    # Higher timeframe → less noise, fewer and more deliberate trades.
    timeframe = "1h"

    # --- Indicator periods (named — no magic numbers) ---
    EMA_FAST = 50
    EMA_SLOW = 200
    RSI_PERIOD = 14
    ADX_PERIOD = 14
    VOLUME_MA_PERIOD = 20

    # --- Signal thresholds ---
    RSI_MIDLINE = 50  # momentum turn level for entries
    RSI_OVERBOUGHT = 70  # do not buy into an overbought market
    RSI_EXIT = 75  # lock gains when momentum is stretched
    ADX_TREND_MIN = 20  # minimum trend strength to trade

    # --- Exit policy (conservative, capital-preservation first) ---
    minimal_roi = {"0": 0.05, "120": 0.03, "360": 0.015, "720": 0.005}
    stoploss = -0.05  # hard 5% stop

    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    process_only_new_candles = True
    # EMA_SLOW + buffer so the slow EMA is valid from the first tradable candle.
    startup_candle_count: int = 250

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.EMA_FAST)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.EMA_SLOW)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.RSI_PERIOD)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=self.ADX_PERIOD)
        dataframe["volume_ma"] = dataframe["volume"].rolling(self.VOLUME_MA_PERIOD).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        in_uptrend = (dataframe["ema_fast"] > dataframe["ema_slow"]) & (
            dataframe["close"] > dataframe["ema_fast"]
        )
        momentum_turn = qtpylib.crossed_above(dataframe["rsi"], self.RSI_MIDLINE)
        not_overbought = dataframe["rsi"] < self.RSI_OVERBOUGHT
        strong_trend = dataframe["adx"] > self.ADX_TREND_MIN
        volume_ok = (dataframe["volume"] > dataframe["volume_ma"]) & (dataframe["volume"] > 0)

        dataframe.loc[
            in_uptrend & momentum_turn & not_overbought & strong_trend & volume_ok,
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trend_break = qtpylib.crossed_below(dataframe["close"], dataframe["ema_fast"])
        overbought = dataframe["rsi"] > self.RSI_EXIT

        dataframe.loc[trend_break | overbought, "exit_long"] = 1
        return dataframe
