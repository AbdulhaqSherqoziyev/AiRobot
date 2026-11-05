"""Jesse-style strategies expressed as data, plus the research RSI+EMA strategy.

A spec mirrors Jesse's should_long / update_position split, but is plain data and runs on the
Rule Builder and the Quant Lab engines. Jesse itself is never imported: its pins conflict with
this project, and a Jesse Strategy class is executable code that needs its whole runtime.
Execution assumptions differ from Jesse; see docs in `.ai/integrations/`.
"""

from __future__ import annotations

import pandas as pd

from quantlab.strategies import indicators as ind
from quantlab.strategies.base import Param, RiskDefaults, Strategy
from quantlab.strategies.rules import RuleBuilder
from quantlab.strategies.technical import cross_down, cross_up

AUDITED_VERSION = "3.6.0"
OPS = {"<": "lt", ">": "gt", "<=": "le", ">=": "ge", "crosses_above": "xa", "crosses_below": "xb"}
SOURCES = {"close", "open", "high", "low", "volume"}


class UnsupportedSpec(ValueError):
    """Names what cannot be represented, instead of silently approximating it."""


def _term(t: dict | str | float, prm: dict, ema_slots: list[int]) -> tuple[str, str]:
    """Returns (kind, value) of one operand, allocating the two EMA slots of the builder."""
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return "num", t
    if isinstance(t, str):
        if t not in SOURCES:
            raise UnsupportedSpec(f"noma'lum narx manbasi: {t}")
        return "ind", t
    name, period = t.get("indicator"), t.get("period")
    if name == "rsi":
        if prm.setdefault("rsiP", period or 14) != (period or 14):
            raise UnsupportedSpec("bitta strategiyada ikki xil RSI davri qo'llab-quvvatlanmaydi")
        return "ind", "rsi"
    if name == "ema":
        if period is None:
            raise UnsupportedSpec("ema uchun period shart")
        if period in ema_slots:
            return "ind", "emaF" if ema_slots.index(period) == 0 else "emaS"
        if len(ema_slots) == 2:
            raise UnsupportedSpec("ikkitadan ortiq EMA qo'llab-quvvatlanmaydi")
        ema_slots.append(period)
        slot = "emaF" if len(ema_slots) == 1 else "emaS"
        prm[slot] = period
        return "ind", slot
    raise UnsupportedSpec(f"indikator qo'llab-quvvatlanmaydi: {name}")


def spec_to_rules(spec: dict) -> dict:
    """Converts a spec to Rule Builder rules. Raises UnsupportedSpec on anything it cannot honour."""
    if spec.get("side", "long") != "long" or spec.get("should_short"):
        raise UnsupportedSpec("faqat Spot long: should_short mumkin emas")
    if spec.get("order_type", "market") != "market":
        raise UnsupportedSpec(f"buyurtma turi qo'llab-quvvatlanmaydi: {spec.get('order_type')}")
    for bad in ("hyperparameters_code", "filters_code", "before_code", "after_code", "take_profit_ladder"):
        if spec.get(bad):
            raise UnsupportedSpec(f"qo'llab-quvvatlanmaydi: {bad}")
    prm: dict = {}
    slots: list[int] = []

    def convert(conds: list[dict]) -> list[dict]:
        out = []
        for c in conds:
            if c.get("op") not in OPS:
                raise UnsupportedSpec(f"noma'lum operator: {c.get('op')}")
            lk, lv = _term(c["left"], prm, slots)
            if lk == "num":
                raise UnsupportedSpec("chap tomon indikator bo'lishi kerak")
            rk, rv = _term(c["right"], prm, slots)
            out.append({"ind": lv, "op": OPS[c["op"]], "kind": rk, "val": rv})
        return out

    if not spec.get("should_long"):
        raise UnsupportedSpec("should_long bo'sh")
    return {"entry": convert(spec["should_long"]), "exit": convert(spec.get("update_position_exit") or []), "join": {"entry": "AND", "exit": "OR"}, "prm": prm}


JESSE_SPECS: dict[str, dict] = {
    "jesse_ema_cross": {
        "name": "Jesse EMA Cross", "jesse_class": "QlEmaCross", "version": "1", "stake_pct": 0.95, "order_type": "market",
        "should_long": [{"left": {"indicator": "ema", "period": 20}, "op": "crosses_above", "right": {"indicator": "ema", "period": 50}}],
        "update_position_exit": [{"left": {"indicator": "ema", "period": 20}, "op": "crosses_below", "right": {"indicator": "ema", "period": 50}}],
    },
    "jesse_rsi_trend": {
        "name": "Jesse RSI Trend", "jesse_class": "QlRsiTrend", "version": "1", "stake_pct": 0.95, "order_type": "market",
        "should_long": [
            {"left": {"indicator": "rsi", "period": 14}, "op": "crosses_above", "right": 40},
            {"left": "close", "op": ">", "right": {"indicator": "ema", "period": 100}},
        ],
        "update_position_exit": [{"left": {"indicator": "rsi", "period": 14}, "op": ">=", "right": 65}],
    },
}


class _SpecStrategy(RuleBuilder):
    key = ""  # otherwise the inherited key would replace the real Rule Builder in the registry
    seedable = False
    spec_key = ""

    def signals(self, df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        return super().signals(df, {"rules": spec_to_rules(JESSE_SPECS[self.spec_key])})


class JesseEmaCross(_SpecStrategy):
    """Jesse spec: long when EMA20 crosses above EMA50, liquidate on the opposite cross."""
    key, name, color, spec_key = "jesse_ema_cross", "Jesse EMA Cross", "#22C55E", "jesse_ema_cross"
    description, indicators = "Example strategy imported from a Jesse-style spec.", ("ema",)
    risk = RiskDefaults(stoploss_pct=0.0)


class JesseRsiTrend(_SpecStrategy):
    """Jesse spec: long when RSI14 crosses above 40 and close is above EMA100, exit at RSI 65."""
    key, name, color, spec_key = "jesse_rsi_trend", "Jesse RSI Trend", "#A3E635", "jesse_rsi_trend"
    description, indicators = "Example strategy imported from a Jesse-style spec.", ("rsi", "ema")
    risk = RiskDefaults(stoploss_pct=0.0)


class RsiEmaTrend(Strategy):
    """Enter when RSI crosses above the entry level with fast EMA above slow; exit at the RSI exit level or on the bearish EMA cross."""
    key, name, color = "rsi_ema_trend", "RSI + EMA Trend (research)", "#F59E0B"
    description, indicators = "Research-only strategy for parameter sweeps. Not seeded into paper trading.", ("rsi", "ema")
    seedable = False
    params = {
        "rsi_period": Param(14, 5, 50), "rsi_entry": Param(30, 10, 50), "rsi_exit": Param(70, 50, 90),
        "ema_fast": Param(10, 3, 50), "ema_slow": Param(50, 10, 200),
    }

    def compute(self, df, p):
        r = ind.rsi(df["close"], p["rsi_period"])
        f, s = ind.ema(df["close"], p["ema_fast"]), ind.ema(df["close"], p["ema_slow"])
        return cross_up(r, p["rsi_entry"]) & (f > s), (r >= p["rsi_exit"]) | cross_down(f, s)


# Verified by the tests against Jesse's own indicator code, candle for candle after warm-up.
SUPPORTED_INDICATORS = {
    "rsi": {"ours": "indicators.rsi", "verified": True, "note": "Bir xil Wilder; birinchi ~100 shamda isinish qiymati farq qiladi"},
    "ema": {"ours": "indicators.ema", "verified": True, "note": "To'liq mos"},
    "sma": {"ours": "indicators.sma", "verified": True, "note": "To'liq mos"},
    "macd": {"ours": "indicators.macd", "verified": True, "note": "Signal chizig'i isinishda farq qiladi"},
    "bollinger_bands": {"ours": "indicators.bollinger", "verified": True, "note": "To'liq mos"},
    "atr": {"ours": "indicators.atr", "verified": True, "note": "Isinishda farq qiladi"},
    "adx": {"ours": "indicators.adx", "verified": True, "note": "Isinishda farq qiladi"},
}


def compatibility_report() -> dict:
    """What a Jesse strategy can and cannot carry over, as audited from Jesse's source."""
    from quantlab.config import TIMEFRAMES

    all_jesse = JESSE_INDICATORS
    jesse_tf = ["1m", "3m", "5m", "15m", "30m", "45m", "1h", "2h", "3h", "4h", "6h", "8h", "12h", "1D", "3D", "1W", "1M"]
    native = {"1D": "1d"}  # Jesse writes the daily timeframe in capitals; 1M there means a month
    ours = {t for t in jesse_tf if native.get(t, t) in TIMEFRAMES}
    return {
        "jesse_version": AUDITED_VERSION, "license": "MIT", "mode": "custom implementation of the concept; Jesse is not a runtime dependency",
        "indicators": {
            "supported": SUPPORTED_INDICATORS,
            "supported_count": len(SUPPORTED_INDICATORS), "jesse_total": len(all_jesse),
            "unsupported": [i for i in all_jesse if i not in SUPPORTED_INDICATORS],
        },
        "order_types": {
            "market": "qo'llab-quvvatlanadi", "limit": "qo'llab-quvvatlanmaydi", "stop": "faqat foiz stop-loss (ExecConfig), kirish uchun emas",
            "stop_limit": "qo'llab-quvvatlanmaydi", "fok": "qo'llab-quvvatlanmaydi",
        },
        "timeframes": {"supported": [t for t in jesse_tf if t in ours], "unsupported": [t for t in jesse_tf if t not in ours]},
        "unsupported_features": [
            "should_short va futures (loyiha faqat Spot long)", "self.buy bilan limit/stop kirish", "qisman chiqish (reduce) va take-profit zinapoyasi",
            "before()/after()/filters() ichidagi ixtiyoriy Python kodi: spec faqat ma'lumot", "bir strategiyada bir nechta route/juftlik",
            "hyperparameters/dna (bu yerda sweep grid ishlatiladi)", "1 daqiqalik sham ichidagi simulyatsiya",
        ],
        "execution_differences": [
            {"topic": "Bajarilish vaqti", "jesse": "Bozor buyurtmasi signal shami yopilish narxida, o'sha zahoti", "quantlab": "Keyingi shamning ochilish narxida"},
            {"topic": "Slippage", "jesse": "Backtest kodida yo'q (3.6.0 manbasi tekshirildi)", "quantlab": "Har ikki oyoqda foiz sifatida"},
            {"topic": "Komissiya", "jesse": "Foiz, config.fee", "quantlab": "Foiz, ExecConfig.fee"},
            {"topic": "Stop", "jesse": "1 daqiqalik shamlar ichida tekshiriladi", "quantlab": "Strategiya taymfreymi shami ichida; bir shamda stop va TP bo'lsa stop ustun"},
            {"topic": "Birja cheklovlari", "jesse": "Min notional/step simulyatsiya qilinmaydi", "quantlab": "Min notional va step size qo'llanadi"},
            {"topic": "Ma'lumot", "jesse": "1 daqiqalik manba shamlar talab qilinadi", "quantlab": "Strategiya taymfreymidagi shamlar"},
        ],
    }


JESSE_INDICATORS = (
    "acosc",
    "ad",
    "adosc",
    "adx",
    "adxr",
    "alligator",
    "alma",
    "ao",
    "apo",
    "aroon",
    "aroonosc",
    "atr",
    "avgprice",
    "bandpass",
    "beta",
    "bollinger_bands",
    "bollinger_bands_width",
    "bop",
    "cc",
    "cci",
    "cfo",
    "cg",
    "chande",
    "chop",
    "cksp",
    "cmo",
    "correl",
    "correlation_cycle",
    "cvi",
    "cwma",
    "damiani_volatmeter",
    "dec_osc",
    "decycler",
    "dema",
    "devstop",
    "di",
    "dm",
    "donchian",
    "dpo",
    "dti",
    "dx",
    "edcf",
    "efi",
    "ema",
    "emd",
    "emv",
    "epma",
    "er",
    "eri",
    "fisher",
    "fosc",
    "frama",
    "fwma",
    "gatorosc",
    "gauss",
    "heikin_ashi_candles",
    "high_pass",
    "high_pass_2_pole",
    "hma",
    "hull_suit",
    "hurst_exponent",
    "hwma",
    "ichimoku_cloud",
    "ichimoku_cloud_seq",
    "ift_rsi",
    "itrend",
    "jma",
    "jsa",
    "kama",
    "kaufmanstop",
    "kdj",
    "keltner",
    "kst",
    "kurtosis",
    "kvo",
    "linearreg",
    "linearreg_angle",
    "linearreg_intercept",
    "linearreg_slope",
    "lrsi",
    "ma",
    "maaq",
    "mab",
    "macd",
    "mama",
    "marketfi",
    "mass",
    "mcginley_dynamic",
    "mean_ad",
    "median_ad",
    "medprice",
    "mfi",
    "midpoint",
    "midprice",
    "minmax",
    "mom",
    "mwdx",
    "natr",
    "nma",
    "nvi",
    "obv",
    "pfe",
    "pivot",
    "pma",
    "ppo",
    "pvi",
    "pwma",
    "qstick",
    "reflex",
    "rma",
    "roc",
    "rocp",
    "rocr",
    "rocr100",
    "roofing",
    "rsi",
    "rsmk",
    "rsx",
    "rvi",
    "safezonestop",
    "sar",
    "settings.jsonc",
    "sinwma",
    "skew",
    "sma",
    "smma",
    "squeeze_momentum",
    "sqwma",
    "srsi",
    "srwma",
    "stc",
    "stddev",
    "stiffness",
    "stochastic",
    "stochf",
    "supersmoother",
    "supersmoother_3_pole",
    "supertrend",
    "support_resistance_with_break",
    "swma",
    "t3",
    "tema",
    "trange",
    "trendflex",
    "trima",
    "trix",
    "tsf",
    "tsi",
    "ttm_squeeze",
    "ttm_trend",
    "typprice",
    "ui",
    "ultosc",
    "var",
    "vi",
    "vidya",
    "vlma",
    "volume",
    "vosc",
    "voss",
    "vpci",
    "vpt",
    "vpwma",
    "vwap",
    "vwma",
    "vwmacd",
    "wad",
    "waddah_attr_explosion",
    "wclprice",
    "wilders",
    "willr",
    "wma",
    "wt",
    "zlema",
    "zscore",
)
