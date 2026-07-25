"""Tests for the startup risk-policy validator (bounded exposure)."""

import pytest

from freqtrade.exceptions import ConfigurationError
from freqtrade.islamic import validate_risk_config


@pytest.mark.parametrize("max_open_trades", [1, 3, 10, 100])
def test_accepts_finite_positive(default_conf, max_open_trades) -> None:
    default_conf["max_open_trades"] = max_open_trades
    validate_risk_config(default_conf)  # must not raise


@pytest.mark.parametrize("max_open_trades", [-1, 0, float("inf")])
def test_rejects_unbounded(default_conf, max_open_trades) -> None:
    default_conf["max_open_trades"] = max_open_trades
    with pytest.raises(ConfigurationError, match="max_open_trades"):
        validate_risk_config(default_conf)


def test_rejects_missing(default_conf) -> None:
    default_conf.pop("max_open_trades", None)
    with pytest.raises(ConfigurationError, match="max_open_trades"):
        validate_risk_config(default_conf)


def test_worker_refuses_unbounded_exposure(default_conf, mocker) -> None:
    """The trading entry point aborts on an unbounded-exposure config."""
    from freqtrade.worker import Worker

    default_conf["max_open_trades"] = -1
    mocker.patch("freqtrade.configuration.Configuration.get_config", return_value=default_conf)
    with pytest.raises(ConfigurationError, match="max_open_trades"):
        Worker(args=None, config=None)
