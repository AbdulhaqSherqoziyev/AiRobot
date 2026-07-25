"""Tests for calendar-period max-loss protections (risk engine)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from freqtrade.plugins.protectionmanager import ProtectionManager
from freqtrade.plugins.protections.max_loss_protection import MaxDailyLoss, MaxWeeklyLoss


# A Wednesday, 14:30 UTC.
_NOW = datetime(2026, 7, 15, 14, 30, tzinfo=UTC)


def _conf():
    return {"timeframe": "5m", "stake_currency": "USDT"}


def _mock_trades(mocker, profits: list[float]) -> None:
    trades = [MagicMock(close_profit_abs=p) for p in profits]
    mocker.patch(
        "freqtrade.plugins.protections.max_loss_protection.Trade.get_trades_proxy",
        return_value=trades,
    )


def test_daily_period_bounds() -> None:
    p = MaxDailyLoss(_conf(), {"max_allowed_loss": 0.05})
    start, end = p._period_bounds(_NOW)
    assert start == datetime(2026, 7, 15, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 16, 0, 0, tzinfo=UTC)


def test_weekly_period_bounds_starts_monday() -> None:
    p = MaxWeeklyLoss(_conf(), {"max_allowed_loss": 0.05})
    start, end = p._period_bounds(_NOW)
    # Monday of that week is 2026-07-13.
    assert start == datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 20, 0, 0, tzinfo=UTC)


def test_no_lock_without_trades(mocker) -> None:
    _mock_trades(mocker, [])
    p = MaxDailyLoss(_conf(), {"max_allowed_loss": 0.05})
    assert p.global_stop(_NOW, "long", 1000.0) is None


def test_no_lock_on_net_profit(mocker) -> None:
    _mock_trades(mocker, [50.0, -10.0])  # net +40
    p = MaxDailyLoss(_conf(), {"max_allowed_loss": 0.05})
    assert p.global_stop(_NOW, "long", 1000.0) is None


def test_no_lock_below_threshold(mocker) -> None:
    _mock_trades(mocker, [-30.0])  # 3% of 1000, below 5%
    p = MaxDailyLoss(_conf(), {"max_allowed_loss": 0.05})
    assert p.global_stop(_NOW, "long", 1000.0) is None


def test_lock_at_threshold(mocker) -> None:
    _mock_trades(mocker, [-40.0, -20.0])  # 6% of 1000, above 5%
    p = MaxDailyLoss(_conf(), {"max_allowed_loss": 0.05})
    result = p.global_stop(_NOW, "long", 1000.0)
    assert result is not None
    assert result.lock is True
    assert result.until == datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
    assert "day loss" in result.reason


def test_weekly_lock_until_next_monday(mocker) -> None:
    _mock_trades(mocker, [-100.0])  # 10% of 1000
    p = MaxWeeklyLoss(_conf(), {"max_allowed_loss": 0.05})
    result = p.global_stop(_NOW, "long", 1000.0)
    assert result is not None
    assert result.until == datetime(2026, 7, 20, 0, 0, tzinfo=UTC)


def test_inert_when_unconfigured(mocker) -> None:
    _mock_trades(mocker, [-500.0])  # huge loss
    p = MaxDailyLoss(_conf(), {})  # no max_allowed_loss -> inert
    assert p.global_stop(_NOW, "long", 1000.0) is None


def test_inert_when_no_starting_balance(mocker) -> None:
    _mock_trades(mocker, [-500.0])
    p = MaxDailyLoss(_conf(), {"max_allowed_loss": 0.05})
    assert p.global_stop(_NOW, "long", 0.0) is None


def test_stop_per_pair_never_locks(mocker) -> None:
    _mock_trades(mocker, [-500.0])
    p = MaxDailyLoss(_conf(), {"max_allowed_loss": 0.05})
    assert p.stop_per_pair("BTC/USDT", _NOW, "long", 1000.0) is None


@pytest.mark.parametrize("method", ["MaxDailyLoss", "MaxWeeklyLoss"])
def test_loaded_by_protection_manager(default_conf, method) -> None:
    """Resolver discovery + config acceptance for both protections."""
    protconf = [{"method": method, "max_allowed_loss": 0.05}]
    man = ProtectionManager(default_conf, protconf)
    assert method in man.short_desc()[0]
