"""Tests for the consecutive-loss circuit breaker (risk engine)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from freqtrade.plugins.protectionmanager import ProtectionManager
from freqtrade.plugins.protections.consecutive_loss_guard import ConsecutiveLossGuard


_NOW = datetime(2026, 7, 15, 14, 30, tzinfo=UTC)


def _conf():
    return {"timeframe": "5m", "stake_currency": "USDT"}


def _mock_trades(mocker, profits_newest_first: list[float]) -> None:
    """Build mock closed trades; first element is the most recent."""
    trades = []
    for i, profit in enumerate(profits_newest_first):
        close_date = _NOW - timedelta(minutes=i + 1)
        trades.append(
            MagicMock(close_profit=profit, close_date=close_date, close_date_utc=close_date)
        )
    # Return in arbitrary order; the guard sorts by close_date.
    mocker.patch(
        "freqtrade.plugins.protections.consecutive_loss_guard.Trade.get_trades_proxy",
        return_value=list(reversed(trades)),
    )


def _guard(stop_candles: int = 12, trade_limit: int = 4):
    return ConsecutiveLossGuard(
        _conf(),
        {
            "trade_limit": trade_limit,
            "stop_duration_candles": stop_candles,
            "lookback_period": 1440,
        },
    )


def test_no_lock_below_streak(mocker) -> None:
    _mock_trades(mocker, [-1.0, -1.0, -1.0])  # 3 losses, limit 4
    assert _guard().global_stop(_NOW, "long", 1000.0) is None


def test_lock_at_streak(mocker) -> None:
    _mock_trades(mocker, [-1.0, -1.0, -1.0, -1.0])  # 4 losses
    result = _guard().global_stop(_NOW, "long", 1000.0)
    assert result is not None and result.lock is True
    assert "consecutive" in result.reason


def test_streak_broken_by_recent_win(mocker) -> None:
    # Most recent trade is a win -> streak resets to 0.
    _mock_trades(mocker, [1.0, -1.0, -1.0, -1.0, -1.0])
    assert _guard().global_stop(_NOW, "long", 1000.0) is None


def test_only_leading_losses_count(mocker) -> None:
    # 3 recent losses then a win then more losses: leading streak = 3 < 4.
    _mock_trades(mocker, [-1.0, -1.0, -1.0, 1.0, -1.0, -1.0])
    assert _guard().global_stop(_NOW, "long", 1000.0) is None


def test_no_trades(mocker) -> None:
    _mock_trades(mocker, [])
    assert _guard().global_stop(_NOW, "long", 1000.0) is None


def test_stop_per_pair_never_locks(mocker) -> None:
    _mock_trades(mocker, [-1.0, -1.0, -1.0, -1.0])
    assert _guard().stop_per_pair("BTC/USDT", _NOW, "long", 1000.0) is None


def test_loaded_by_protection_manager(default_conf) -> None:
    protconf = [{"method": "ConsecutiveLossGuard", "trade_limit": 3, "stop_duration": 60}]
    man = ProtectionManager(default_conf, protconf)
    assert "ConsecutiveLossGuard" in man.short_desc()[0]
