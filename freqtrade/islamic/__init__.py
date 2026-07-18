"""Islamic Spot Trading Platform - Sharia-compliance guards."""

from freqtrade.islamic.compliance import (
    SPOT_ONLY_ENFORCED_KEY,
    assert_spot_config,
    assert_spot_operation,
    enforce_spot_only,
    spot_only_enforced,
)


__all__ = [
    "SPOT_ONLY_ENFORCED_KEY",
    "assert_spot_config",
    "assert_spot_operation",
    "enforce_spot_only",
    "spot_only_enforced",
]
