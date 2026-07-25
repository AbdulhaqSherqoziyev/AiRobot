"""
Startup risk-policy validation (risk engine — capital preservation).

Freqtrade already enforces position sizing at runtime via ``stake_amount``
(per-position cap), ``max_open_trades`` (concurrent positions) and
``tradable_balance_ratio`` (total deployable capital). The failure mode this guard
closes is a *reckless configuration* that leaves total exposure unbounded — most
notably an unlimited ``max_open_trades``.

Applied at the trading entry point when spot-only enforcement is armed, so the
platform refuses to start with an unbounded-exposure configuration. Fails closed.
"""

import logging

from freqtrade.constants import Config
from freqtrade.exceptions import ConfigurationError


logger = logging.getLogger(__name__)


def validate_risk_config(config: Config) -> None:
    """
    Enforce the platform's minimum risk policy on the configuration.

    :raises ConfigurationError: if total exposure is not bounded
        (``max_open_trades`` unlimited or non-positive).
    """
    max_open_trades = config.get("max_open_trades")

    # -1 (and, after processing, ``inf``) means unlimited in Freqtrade.
    is_unlimited = (
        max_open_trades is None
        or max_open_trades == -1
        or (isinstance(max_open_trades, float) and max_open_trades == float("inf"))
    )
    if is_unlimited or max_open_trades <= 0:
        raise ConfigurationError(
            "Platform risk policy: `max_open_trades` must be a finite positive number "
            "to bound total exposure (capital preservation). Unlimited open trades are "
            f"not allowed (got {max_open_trades!r})."
        )

    logger.info(
        "Risk policy: bounded exposure confirmed (max_open_trades=%s).", max_open_trades
    )
