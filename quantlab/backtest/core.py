"""Candle-by-candle spot simulation shared by the backtester and the paper engine.

Rules: a signal computed from candle i can only execute at the open of candle i+1. Long
only, no leverage, fees and slippage on both legs, exchange minimums enforced. When stop
and take-profit could both trigger inside one candle the stop wins (conservative).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Filters:
    min_notional: float = 5.0
    step_size: float = 0.0
    min_qty: float = 0.0

    def round_qty(self, qty: float) -> float:
        if self.step_size > 0:
            return math.floor(qty / self.step_size + 1e-9) * self.step_size
        return qty


@dataclass(frozen=True)
class ExecConfig:
    fee: float = 0.001
    slippage: float = 0.0005
    stake_pct: float = 1.0  # fraction of equity per position
    stoploss_pct: float = 0.0  # 0 disables
    takeprofit_pct: float = 0.0
    filters: Filters = Filters()


@dataclass
class Position:
    entry_ts: int
    entry_price: float
    qty: float
    entry_fee: float
    signal_ts: int


@dataclass
class Fill:
    side: str
    ts: int
    price: float
    qty: float
    fee: float
    reason: str
    signal_ts: int = 0
    pnl: float = 0.0
    pnl_pct: float = 0.0


@dataclass
class SimState:
    usdt: float
    position: Position | None = None
    pending: str | None = None  # 'enter' | 'exit', to execute at the next open
    pending_ts: int = 0
    pending_stake: float | None = None  # size decided at signal time, from data known then
    rejected: list[str] = field(default_factory=list)

    def equity(self, price: float) -> float:
        return self.usdt + (self.position.qty * price if self.position else 0.0)

    def to_dict(self) -> dict:
        return asdict(self)


def _buy(state: SimState, cfg: ExecConfig, ts: int, open_price: float, signal_ts: int) -> Fill | None:
    price = open_price * (1 + cfg.slippage)
    stake = state.pending_stake if state.pending_stake is not None else cfg.stake_pct
    quote = state.equity(open_price) * stake
    quote = min(quote, state.usdt)
    # Fee is taken from the spend, so the balance can never go negative.
    qty = cfg.filters.round_qty(quote / (price * (1 + cfg.fee)))
    cost = qty * price
    if qty <= 0 or qty < cfg.filters.min_qty or cost < cfg.filters.min_notional:
        state.rejected.append(f"{ts}: order {cost:.2f} USDT below exchange minimum")
        return None
    fee = cost * cfg.fee
    state.usdt -= cost + fee
    state.position = Position(ts, price, qty, fee, signal_ts)
    return Fill("buy", ts, price, qty, fee, "signal", signal_ts)


def _sell(state: SimState, cfg: ExecConfig, ts: int, raw_price: float, reason: str) -> Fill:
    pos = state.position
    assert pos is not None
    price = raw_price * (1 - cfg.slippage)
    proceeds = pos.qty * price
    fee = proceeds * cfg.fee
    state.usdt += proceeds - fee
    pnl = proceeds - fee - pos.qty * pos.entry_price - pos.entry_fee
    basis = pos.qty * pos.entry_price + pos.entry_fee
    state.position = None
    return Fill("sell", ts, price, pos.qty, fee, reason, pos.signal_ts, pnl, pnl / basis * 100 if basis else 0.0)


def on_candle(state: SimState, cfg: ExecConfig, ts: int, o: float, h: float, l: float, c: float, enter: bool, exit_: bool, allow_entries: bool = True, stake: float | None = None) -> list[Fill]:
    """Advance one closed candle: execute last candle's signal at this open, check stops,
    then record this candle's signal for the next open."""
    fills: list[Fill] = []
    if state.pending == "enter" and state.position is None and allow_entries:
        if (f := _buy(state, cfg, ts, o, state.pending_ts)):
            fills.append(f)
    elif state.pending == "exit" and state.position is not None:
        fills.append(_sell(state, cfg, ts, o, "signal"))
    state.pending = None

    if state.position is not None:
        entry = state.position.entry_price
        stop = entry * (1 - cfg.stoploss_pct) if cfg.stoploss_pct > 0 else None
        tp = entry * (1 + cfg.takeprofit_pct) if cfg.takeprofit_pct > 0 else None
        if stop is not None and l <= stop:
            # A gap through the stop fills at the open, not at the stop price.
            fills.append(_sell(state, cfg, ts, min(stop, o), "stoploss"))
        elif tp is not None and h >= tp:
            fills.append(_sell(state, cfg, ts, max(tp, o), "takeprofit"))

    if state.position is None and enter:
        state.pending, state.pending_ts, state.pending_stake = "enter", ts, stake
    elif state.position is not None and exit_:
        state.pending, state.pending_ts = "exit", ts
    return fills
