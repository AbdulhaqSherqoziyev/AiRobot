"""Integration tests for IslamicComplianceFilter (loaded via the real resolver)."""

from unittest.mock import MagicMock

import pytest

from freqtrade.plugins.pairlistmanager import PairListManager
from freqtrade.resolvers import PairListResolver
from tests.conftest import get_patched_freqtradebot


def _make_filter(mocker, default_conf, pairlistconfig=None):
    freqtrade = get_patched_freqtradebot(mocker, default_conf)
    plm = PairListManager(freqtrade.exchange, default_conf, MagicMock())
    return PairListResolver.load_pairlist(
        "IslamicComplianceFilter",
        freqtrade.exchange,
        plm,
        default_conf,
        pairlistconfig or {},
        1,
    )


@pytest.fixture
def sample_pairs():
    return [
        "BTC/USDT",
        "ETH/USDT",
        "BTCUP/USDT",
        "BTCDOWN/USDT",
        "ETH3L/USDT",
        "SOLBULL/USDT",
        "JUP/USDT",  # false-positive guard: must survive
    ]


def test_filter_removes_leveraged_tokens(mocker, default_conf, sample_pairs) -> None:
    flt = _make_filter(mocker, default_conf)
    result = flt.filter_pairlist(list(sample_pairs), {})
    assert result == ["BTC/USDT", "ETH/USDT", "JUP/USDT"]


def test_filter_audit_mode_keeps_all(mocker, default_conf, sample_pairs) -> None:
    flt = _make_filter(mocker, default_conf, {"audit_mode": True})
    result = flt.filter_pairlist(list(sample_pairs), {})
    assert result == sample_pairs


def test_filter_blacklist(mocker, default_conf) -> None:
    flt = _make_filter(mocker, default_conf, {"blacklist": ["ETH"]})
    result = flt.filter_pairlist(["BTC/USDT", "ETH/USDT"], {})
    assert result == ["BTC/USDT"]


def test_filter_allowlist_protects_false_positive(mocker, default_conf) -> None:
    flt = _make_filter(mocker, default_conf, {"allowlist": ["BTCUP/USDT"]})
    result = flt.filter_pairlist(["BTC/USDT", "BTCUP/USDT"], {})
    assert result == ["BTC/USDT", "BTCUP/USDT"]


def test_filter_custom_suffixes(mocker, default_conf) -> None:
    flt = _make_filter(mocker, default_conf, {"leverage_suffixes": ["HALF"]})
    result = flt.filter_pairlist(["BTCHALF/USDT", "BTCUP/USDT"], {})
    # Only the custom suffix is screened; default UP no longer applies.
    assert result == ["BTCUP/USDT"]


def test_filter_short_desc(mocker, default_conf) -> None:
    flt = _make_filter(mocker, default_conf)
    assert "Sharia" in flt.short_desc()
    audit = _make_filter(mocker, default_conf, {"audit_mode": True})
    assert "audit" in audit.short_desc()
