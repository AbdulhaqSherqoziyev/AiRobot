"""Islamic Spot Trading Platform - Sharia-compliance guards."""

from freqtrade.islamic.compliance import (
    SPOT_ONLY_ENFORCED_KEY,
    assert_spot_config,
    assert_spot_operation,
    enforce_spot_only,
    spot_only_enforced,
)
from freqtrade.islamic.order_gate import order_compliance_reason
from freqtrade.islamic.risk_config import validate_risk_config
from freqtrade.islamic.screening import (
    base_currency,
    leveraged_token_reason,
    screen_pair,
)


__all__ = [
    "SPOT_ONLY_ENFORCED_KEY",
    "assert_spot_config",
    "assert_spot_operation",
    "base_currency",
    "enforce_spot_only",
    "leveraged_token_reason",
    "order_compliance_reason",
    "screen_pair",
    "spot_only_enforced",
    "validate_risk_config",
]
