"""
Consecutive-loss circuit breaker (risk engine — capital preservation).

Locks all entries after a run of consecutive losing trades, forcing a cool-down
after a losing streak. The lock is written as a ``PairLock`` and therefore
survives bot restarts, so the halt persists until it expires or is manually
cleared (``/unlock``). Global stop only — exits are never blocked.

Complements upstream ``StoplossGuard`` (which counts stoploss exits within a
window) by reacting to a *streak* of losses regardless of exit reason.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from freqtrade.constants import Config, LongShort
from freqtrade.persistence import Trade
from freqtrade.plugins.protections import IProtection, ProtectionReturn


logger = logging.getLogger(__name__)


class ConsecutiveLossGuard(IProtection):
    """
    Circuit breaker: after ``trade_limit`` consecutive losing trades (within the
    configured lookback), lock all pairs for the configured stop duration.
    """

    has_global_stop: bool = True
    has_local_stop: bool = False

    def __init__(self, config: Config, protection_config: dict[str, Any]) -> None:
        super().__init__(config, protection_config)
        self._trade_limit = int(protection_config.get("trade_limit", 4))

    def short_desc(self) -> str:
        return (
            f"{self.name} - Stop trading after {self._trade_limit} consecutive losing "
            f"trades, locking {self.unlock_reason_time_element}."
        )

    def _reason(self, streak: int) -> str:
        return (
            f"{streak} consecutive losing trades reached the limit of "
            f"{self._trade_limit}, locking {self.unlock_reason_time_element}."
        )

    def _consecutive_losses(self, date_now: datetime) -> ProtectionReturn | None:
        look_back_until = date_now - timedelta(minutes=self._lookback_period)
        trades = Trade.get_trades_proxy(is_open=False, close_date=look_back_until)
        closed = sorted(
            (t for t in trades if t.close_date is not None),
            key=lambda t: t.close_date_utc,
            reverse=True,
        )

        streak = 0
        for trade in closed:
            if (trade.close_profit or 0.0) < 0:
                streak += 1
            else:
                break

        if streak < self._trade_limit:
            return None

        self.log_once(
            f"Trading stopped: {streak} consecutive losing trades reached the "
            f"{self._trade_limit} limit. Locking {self.unlock_reason_time_element}.",
            logger.info,
        )
        return ProtectionReturn(
            lock=True,
            until=self.calculate_lock_end(closed),
            reason=self._reason(streak),
        )

    def global_stop(
        self, date_now: datetime, side: LongShort, starting_balance: float
    ) -> ProtectionReturn | None:
        return self._consecutive_losses(date_now)

    def stop_per_pair(
        self, pair: str, date_now: datetime, side: LongShort, starting_balance: float
    ) -> ProtectionReturn | None:
        return None
