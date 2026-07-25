"""Tests for Sharia instrument screening (.ai/ISLAMIC_POLICY.md layer L5)."""

import pytest

from freqtrade.islamic.screening import (
    base_currency,
    leveraged_token_reason,
    screen_pair,
)


@pytest.mark.parametrize(
    "pair,expected",
    [
        ("BTC/USDT", "BTC"),
        ("eth/usdt", "ETH"),
        (" ada/USDT ", "ADA"),
    ],
)
def test_base_currency(pair, expected) -> None:
    assert base_currency(pair) == expected


@pytest.mark.parametrize(
    "base",
    [
        "BTCUP",
        "BTCDOWN",
        "ETHBULL",
        "ETHBEAR",
        "BTC3L",
        "BTC3S",
        " SOL5L".strip(),
        "ADA3L",
    ],
)
def test_leveraged_token_detected(base) -> None:
    assert leveraged_token_reason(base) is not None


@pytest.mark.parametrize(
    "base",
    [
        "BTC",
        "ETH",
        "JUP",  # ends in "UP" but underlying "J" is too short -> not leveraged
        "UP",  # the suffix itself, no underlying
        "BULL",  # the suffix itself
        "DOWN",
        "1000SATS",  # digits not immediately before final S
        "SOL",
        "3L",  # multiplier with no underlying
    ],
)
def test_legit_token_not_flagged(base) -> None:
    assert leveraged_token_reason(base) is None


def test_screen_pair_leveraged() -> None:
    assert screen_pair("BTCUP/USDT") is not None
    assert screen_pair("BTC3L/USDT") is not None


def test_screen_pair_clean() -> None:
    assert screen_pair("BTC/USDT") is None
    assert screen_pair("JUP/USDT") is None


def test_screen_pair_blacklist_base_and_pair() -> None:
    assert screen_pair("XYZ/USDT", blacklist=frozenset({"XYZ"})) == "compliance blacklist"
    assert screen_pair("XYZ/USDT", blacklist=frozenset({"XYZ/USDT"})) == "compliance blacklist"
    assert screen_pair("BTC/USDT", blacklist=frozenset({"XYZ"})) is None


def test_screen_pair_allowlist_overrides_everything() -> None:
    # Allowlist beats leveraged detection...
    assert screen_pair("BTCUP/USDT", allowlist=frozenset({"BTCUP"})) is None
    # ...and beats the blacklist.
    assert (
        screen_pair("XYZ/USDT", blacklist=frozenset({"XYZ"}), allowlist=frozenset({"XYZ/USDT"}))
        is None
    )


def test_screen_pair_custom_suffixes() -> None:
    # A custom suffix list can catch exchange-specific naming.
    assert screen_pair("BTCHALF/USDT", suffixes=("HALF",)) is not None
    # And the defaults no longer apply when overridden.
    assert screen_pair("BTCUP/USDT", suffixes=("HALF",)) is None
