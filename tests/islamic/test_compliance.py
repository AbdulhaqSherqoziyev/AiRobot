"""Tests for the Sharia-compliance guards (.ai/ISLAMIC_POLICY.md layers L1/L2)."""

import pytest

from freqtrade.exceptions import ConfigurationError, OperationalException
from freqtrade.islamic import (
    SPOT_ONLY_ENFORCED_KEY,
    assert_spot_config,
    assert_spot_operation,
    enforce_spot_only,
    spot_only_enforced,
)


@pytest.mark.parametrize(
    "trading_mode,margin_mode",
    [
        ("spot", ""),
        ("spot", None),
        (None, None),  # unset defaults to spot
    ],
)
def test_assert_spot_config_accepts_spot(default_conf, trading_mode, margin_mode) -> None:
    if trading_mode is None:
        default_conf.pop("trading_mode", None)
    else:
        default_conf["trading_mode"] = trading_mode
    if margin_mode is None:
        default_conf.pop("margin_mode", None)
    else:
        default_conf["margin_mode"] = margin_mode
    assert_spot_config(default_conf)


@pytest.mark.parametrize(
    "trading_mode,margin_mode",
    [
        ("futures", "isolated"),
        ("futures", ""),
        ("margin", "cross"),
        ("margin", ""),
        ("spot", "isolated"),  # margin_mode alone is already forbidden
        ("spot", "cross"),
    ],
)
def test_assert_spot_config_rejects_non_spot(default_conf, trading_mode, margin_mode) -> None:
    default_conf["trading_mode"] = trading_mode
    default_conf["margin_mode"] = margin_mode
    with pytest.raises(ConfigurationError, match="Islamic compliance"):
        assert_spot_config(default_conf)


def test_enforce_spot_only_arms_marker(default_conf) -> None:
    assert not spot_only_enforced(default_conf)
    enforce_spot_only(default_conf)
    assert spot_only_enforced(default_conf)
    assert default_conf[SPOT_ONLY_ENFORCED_KEY] is True


def test_enforce_spot_only_rejects_and_does_not_arm(default_conf) -> None:
    default_conf["trading_mode"] = "futures"
    default_conf["margin_mode"] = "isolated"
    with pytest.raises(ConfigurationError, match="Islamic compliance"):
        enforce_spot_only(default_conf)
    assert not spot_only_enforced(default_conf)


def test_assert_spot_operation_blocks_armed_config(default_conf) -> None:
    # Unarmed config (library/backtesting use): operation passes through.
    assert_spot_operation(default_conf, "set_leverage")

    enforce_spot_only(default_conf)
    with pytest.raises(OperationalException, match=r"set_leverage.*forbidden"):
        assert_spot_operation(default_conf, "set_leverage")


def test_exchange_leverage_paths_blocked_when_armed(default_conf, mocker) -> None:
    """L2 integration: an armed bot's exchange refuses leverage/margin calls."""
    from tests.conftest import get_patched_exchange

    enforce_spot_only(default_conf)
    # Simulate live mode - the guard must fire before any dry-run early-return.
    default_conf["dry_run"] = False
    exchange = get_patched_exchange(mocker, default_conf)

    with pytest.raises(OperationalException, match="Islamic compliance"):
        exchange._set_leverage(2.0, "BTC/USDT")
    with pytest.raises(OperationalException, match="Islamic compliance"):
        exchange.set_margin_mode("BTC/USDT", margin_mode=mocker.MagicMock())


def test_worker_refuses_non_spot_config(default_conf, mocker) -> None:
    """L1 integration: the trading entry point aborts on a futures config."""
    from freqtrade.worker import Worker

    default_conf["trading_mode"] = "futures"
    default_conf["margin_mode"] = "isolated"
    mocker.patch("freqtrade.configuration.Configuration.get_config", return_value=default_conf)
    with pytest.raises(ConfigurationError, match="Islamic compliance"):
        Worker(args=None, config=None)


def test_worker_arms_marker_on_spot_config(default_conf, mocker) -> None:
    """L1 integration: a spot config starts normally and is armed."""
    from freqtrade.worker import Worker

    mocker.patch("freqtrade.configuration.Configuration.get_config", return_value=default_conf)
    mocker.patch("freqtrade.worker.FreqtradeBot", mocker.MagicMock())
    worker = Worker(args=None, config=None)
    assert spot_only_enforced(worker._config)
