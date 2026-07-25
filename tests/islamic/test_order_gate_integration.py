"""Integration tests: execute_entry rejects non-compliant orders (L4 hook)."""

from unittest.mock import MagicMock

import pytest

from freqtrade.islamic import enforce_spot_only, spot_only_enforced
from tests.conftest import EXMS, get_patched_freqtradebot


def _armed_bot(mocker, default_conf_usdt):
    default_conf_usdt["trading_mode"] = "spot"
    freqtrade = get_patched_freqtradebot(mocker, default_conf_usdt)
    enforce_spot_only(freqtrade.config)  # arm the marker (as Worker does in prod)
    assert spot_only_enforced(freqtrade.config)
    return freqtrade


@pytest.mark.parametrize(
    "pair,is_short,leverage",
    [
        ("BTC/USDT", False, 2.0),  # forbidden leverage
        ("BTC/USDT", True, 1.0),  # short selling
        ("BTCUP/USDT", False, 1.0),  # leveraged token
        ("ETH3L/USDT", False, 1.0),  # leveraged token
    ],
)
def test_execute_entry_rejects_noncompliant(
    mocker, default_conf_usdt, pair, is_short, leverage
) -> None:
    freqtrade = _armed_bot(mocker, default_conf_usdt)
    create_mock = MagicMock()
    mocker.patch(f"{EXMS}.create_order", create_mock)
    # Force the computed (price, stake, leverage) so the gate is what decides.
    mocker.patch.object(
        freqtrade,
        "get_valid_enter_price_and_stake",
        return_value=(100.0, 2.0, leverage),
    )

    result = freqtrade.execute_entry(pair, 2.0, is_short=is_short)

    assert result is False
    assert create_mock.call_count == 0  # no order ever reached the exchange


def test_execute_entry_gate_inactive_when_not_armed(mocker, default_conf_usdt) -> None:
    """Without the marker (library/backtest use) the gate must not interfere."""
    default_conf_usdt["trading_mode"] = "spot"
    freqtrade = get_patched_freqtradebot(mocker, default_conf_usdt)
    assert not spot_only_enforced(freqtrade.config)
    # get_valid... returns a non-compliant leverage, but the gate is inactive, so
    # execution proceeds past the gate to create_order.
    create_mock = MagicMock(return_value={"id": "1", "symbol": "BTC/USDT", "status": "open"})
    mocker.patch(f"{EXMS}.create_order", create_mock)
    mocker.patch.object(
        freqtrade,
        "get_valid_enter_price_and_stake",
        return_value=(100.0, 2.0, 2.0),
    )
    # We don't assert full success (order object parsing needs more mocks); we only
    # assert the gate did NOT short-circuit before create_order.
    try:
        freqtrade.execute_entry("BTC/USDT", 2.0)
    except Exception:
        pass
    assert create_mock.call_count == 1
