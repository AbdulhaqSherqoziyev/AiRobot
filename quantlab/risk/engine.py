"""Risk rules shared by paper and live. Pure functions, so every limit is unit tested.
A breached limit blocks new entries only: exits are never blocked by a risk rule."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RiskLimits:
    max_position_usdt: float = 100.0
    max_daily_loss_pct: float = 5.0
    max_drawdown_pct: float = 20.0
    max_simultaneous_positions: int = 1
    max_trade_risk_pct: float = 5.0  # stop distance x position, as % of equity
    max_orders_per_hour: int = 6

    @classmethod
    def from_dict(cls, d: dict | None) -> "RiskLimits":
        fields = cls.__dataclass_fields__
        return cls(**{k: type(getattr(cls, k))(v) for k, v in (d or {}).items() if k in fields})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str


def portfolio_breaches(limits: RiskLimits, equity: float, peak: float, day_start_equity: float) -> list[Violation]:
    """Breaches that halt the portfolio until the owner resumes it."""
    out = []
    if peak > 0:
        dd = (1 - equity / peak) * 100
        if dd >= limits.max_drawdown_pct:
            out.append(Violation("max_drawdown", f"drawdown {dd:.2f}% >= {limits.max_drawdown_pct}%"))
    if day_start_equity > 0:
        loss = (1 - equity / day_start_equity) * 100
        if loss >= limits.max_daily_loss_pct:
            out.append(Violation("daily_loss", f"daily loss {loss:.2f}% >= {limits.max_daily_loss_pct}%"))
    return out


def entry_violations(limits: RiskLimits, *, quote: float, equity: float, free_usdt: float, open_positions: int, orders_last_hour: int, min_notional: float, stoploss_pct: float, duplicate: bool = False) -> list[Violation]:
    """Pre-trade checks for one new entry."""
    out = []
    if duplicate:
        out.append(Violation("duplicate_order", "an order for this signal candle already exists"))
    if quote > limits.max_position_usdt + 1e-9:
        out.append(Violation("max_position", f"{quote:.2f} > {limits.max_position_usdt}"))
    if quote > free_usdt + 1e-9:
        out.append(Violation("insufficient_balance", f"{quote:.2f} > free {free_usdt:.2f}"))
    if quote < min_notional:
        out.append(Violation("min_order", f"{quote:.2f} < exchange minimum {min_notional}"))
    if open_positions >= limits.max_simultaneous_positions:
        out.append(Violation("max_positions", f"{open_positions} open"))
    if orders_last_hour >= limits.max_orders_per_hour:
        out.append(Violation("order_frequency", f"{orders_last_hour} orders in the last hour"))
    if equity > 0 and stoploss_pct > 0 and quote * stoploss_pct / equity * 100 > limits.max_trade_risk_pct:
        out.append(Violation("trade_risk", f"risk {quote * stoploss_pct / equity * 100:.2f}% of equity"))
    if stoploss_pct <= 0:
        out.append(Violation("no_stoploss", "live and paper entries need a stop distance for per-trade risk"))
    return out
