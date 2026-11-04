"""Standard strategy interface. Signals may use only data up to and including candle i;
tests assert this for every registered strategy by truncating the input."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

import pandas as pd

REGISTRY: dict[str, type["Strategy"]] = {}


@dataclass(frozen=True)
class Param:
    default: float
    low: float
    high: float
    step: float = 1
    integer: bool = True
    label: str = ""


@dataclass(frozen=True)
class RiskDefaults:
    stake_pct: float = 0.95
    stoploss_pct: float = 0.03
    takeprofit_pct: float = 0.0
    max_drawdown_pct: float = 20.0
    daily_loss_pct: float = 5.0
    max_orders_per_hour: int = 6


class Strategy(ABC):
    key: str = ""
    name: str = ""
    version: str = "1"
    kind: str = "technical"
    description: str = ""
    pairs: tuple[str, ...] = ()  # empty: any pair in the universe
    timeframes: tuple[str, ...] = ("15m", "30m", "1h", "4h", "1d")
    params: dict[str, Param] = {}
    risk: RiskDefaults = RiskDefaults()
    indicators: tuple[str, ...] = ()
    color: str = "#3B82F6"
    warmup: int = 200
    seedable: bool = True

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        if cls.key:
            REGISTRY[cls.key] = cls

    def resolve(self, params: dict | None) -> dict:
        out = {k: p.default for k, p in self.params.items()}
        for k, v in (params or {}).items():
            if k in self.params:
                p = self.params[k]
                v = float(v)
                if not p.low <= v <= p.high:
                    raise ValueError(f"{self.key}: {k}={v} outside [{p.low}, {p.high}]")
                out[k] = int(v) if p.integer else v
        return out

    @abstractmethod
    def compute(self, df: pd.DataFrame, p: dict) -> tuple[pd.Series, pd.Series]:
        """Boolean entry and exit series aligned with df."""

    def signals(self, df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        enter, exit_ = self.compute(df, self.resolve(params))
        return pd.DataFrame({"enter": enter.fillna(False).astype(bool).to_numpy(), "exit": exit_.fillna(False).astype(bool).to_numpy()}, index=df.index)

    def describe(self) -> dict:
        return {
            "key": self.key, "name": self.name, "version": self.version, "kind": self.kind, "description": self.description,
            "pairs": list(self.pairs), "timeframes": list(self.timeframes), "indicators": list(self.indicators), "color": self.color,
            "params": {k: asdict(v) for k, v in self.params.items()}, "risk": asdict(self.risk),
            "entry_logic": (self.__doc__ or "").strip(),
        }


def get_strategy(key: str) -> Strategy:
    import quantlab.ml.strategy  # noqa: F401  registers ML strategies
    import quantlab.strategies.rules  # noqa: F401
    import quantlab.strategies.technical  # noqa: F401

    return REGISTRY[key]()


def all_strategies() -> list[Strategy]:
    import quantlab.ml.strategy  # noqa: F401
    import quantlab.strategies.rules  # noqa: F401
    import quantlab.strategies.technical  # noqa: F401

    return [cls() for cls in REGISTRY.values()]
