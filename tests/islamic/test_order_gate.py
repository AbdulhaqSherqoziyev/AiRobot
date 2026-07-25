"""Tests for the pre-order compliance gate (.ai/ISLAMIC_POLICY.md layer L4)."""

import pytest

from freqtrade.islamic import order_compliance_reason


def test_gate_allows_clean_long_spot() -> None:
    assert order_compliance_reason("BTC/USDT", is_short=False, leverage=1.0) is None


def test_gate_rejects_short() -> None:
    reason = order_compliance_reason("BTC/USDT", is_short=True, leverage=1.0)
    assert reason is not None and "short" in reason.lower()


@pytest.mark.parametrize("leverage", [1.5, 2.0, 3.0, 0.5, 1.0001])
def test_gate_rejects_leverage(leverage) -> None:
    reason = order_compliance_reason("BTC/USDT", is_short=False, leverage=leverage)
    assert reason is not None and "leverage" in reason.lower()


def test_gate_accepts_leverage_within_epsilon() -> None:
    # A float that is 1.0 within tolerance must pass.
    assert order_compliance_reason("BTC/USDT", is_short=False, leverage=1.0 + 1e-12) is None


@pytest.mark.parametrize("pair", ["BTCUP/USDT", "BTC3L/USDT", "ETHBULL/USDT"])
def test_gate_rejects_leveraged_token(pair) -> None:
    reason = order_compliance_reason(pair, is_short=False, leverage=1.0)
    assert reason is not None and "leveraged" in reason.lower()
