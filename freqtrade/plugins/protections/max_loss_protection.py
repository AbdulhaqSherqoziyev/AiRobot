"""
Calendar-period maximum-loss protections (risk engine — capital preservation).

Complements the upstream rolling-window ``MaxDrawdown`` with hard, calendar-based
loss budgets required by the platform constitution:

* ``MaxDailyLoss``  — realized loss since 00:00 UTC today.
* ``MaxWeeklyLoss`` — realized loss since 00:00 UTC Monday of the current week.

When the realized loss over the current period reaches ``max_allowed_loss``
(a fraction of the starting balance, e.g. ``0.05`` = 5%), all pairs are locked
until the period rolls over (next midnight / next Monday), giving each period a
fresh loss budget. Global stop only; entries are blocked, exits are never.
"""

import logging
from abc import abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from freqtrade.constants import Config, LongShort
from freqtrade.persistence import Trade
from freqtrade.plugins.protections import IProtection, ProtectionReturn


logger = logging.getLogger(__name__)


class _MaxLossProtection(IProtection):
    """
    Shared logic for calendar-period loss limits. Subclasses define the period
    boundaries. Inert (never locks) unless ``max_allowed_loss`` is configured > 0.
    """

    has_global_stop: bool = True
    has_local_stop: bool = False

    # Human-readable period name for messages (e.g. "day", "week").
    period_name: str = "period"

    def __init__(self, config: Config, protection_config: dict[str, Any]) -> None:
        super().__init__(config, protection_config)
        self._max_allowed_loss = float(protection_config.get("max_allowed_loss", 0.0))

    @abstractmethod
    def _period_bounds(self, date_now: datetime) -> tuple[datetime, datetime]:
        """Return (period_start, period_end) in UTC for the period containing date_now."""

    def short_desc(self) -> str:
        return (
            f"{self.name} - Stop trading if realized loss in the current "
            f"{self.period_name} exceeds {self._max_allowed_loss:.1%} of the "
            f"starting balance."
        )

    def _reason(self, loss_ratio: float, period_end: datetime) -> str:
        return (
            f"Max {self.period_name} loss {loss_ratio:.2%} reached "
            f"{self._max_allowed_loss:.2%}; locking until {period_end:%Y-%m-%d %H:%M} UTC."
        )

    def _max_loss(self, date_now: datetime, starting_balance: float) -> ProtectionReturn | None:
        # Inert unless explicitly configured with a positive budget, and only when
        # a meaningful starting balance is known.
        if self._max_allowed_loss <= 0 or starting_balance <= 0:
            return None

        period_start, period_end = self._period_bounds(date_now)
        trades = Trade.get_trades_proxy(is_open=False, close_date=period_start)
        if not trades:
            return None

        realized = sum((trade.close_profit_abs or 0.0) for trade in trades)
        if realized >= 0:
            return None

        loss_ratio = abs(realized) / starting_balance
        if loss_ratio < self._max_allowed_loss:
            return None

        self.log_once(
            f"Trading stopped: {self.period_name} loss {loss_ratio:.2%} reached the "
            f"{self._max_allowed_loss:.2%} limit. Locked until {period_end:%Y-%m-%d %H:%M} UTC.",
            logger.info,
        )
        return ProtectionReturn(
            lock=True,
            until=period_end,
            reason=self._reason(loss_ratio, period_end),
        )

    def global_stop(
        self, date_now: datetime, side: LongShort, starting_balance: float
    ) -> ProtectionReturn | None:
        return self._max_loss(date_now, starting_balance)

    def stop_per_pair(
        self, pair: str, date_now: datetime, side: LongShort, starting_balance: float
    ) -> ProtectionReturn | None:
        return None


class MaxDailyLoss(_MaxLossProtection):
    """Lock all pairs when today's realized loss (since 00:00 UTC) hits the budget."""

    period_name = "day"

    def _period_bounds(self, date_now: datetime) -> tuple[datetime, datetime]:
        start = date_now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)


class MaxWeeklyLoss(_MaxLossProtection):
    """Lock all pairs when this week's realized loss (since 00:00 UTC Monday) hits the budget."""

    period_name = "week"

    def _period_bounds(self, date_now: datetime) -> tuple[datetime, datetime]:
        day_start = date_now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=day_start.weekday())
        return week_start, week_start + timedelta(days=7)
