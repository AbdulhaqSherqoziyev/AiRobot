"""
Sharia-compliance guards for the Islamic Spot Trading Platform.

Implements enforcement layers L1 (configuration) and L2 (exchange operations)
of `.ai/ISLAMIC_POLICY.md`:

* L1 — `enforce_spot_only()` rejects any configuration that is not pure spot
  trading and arms a per-configuration enforcement marker. It is called from the
  trading entry point (`Worker`), so `freqtrade trade` can never run with
  margin, futures, leverage or short selling — in live *and* dry-run mode.
* L2 — `assert_spot_operation()` is called from exchange-level leverage/margin
  mutation paths and raises whenever the marker is armed, so those operations
  stay unreachable even through unforeseen code paths.

The marker travels with the bot's config mapping rather than process-global
state, so library usage (backtesting research, upstream test-suite) is not
affected by an armed trading process.

Guards fail closed: any violation raises, nothing is ever downgraded to a
warning.
"""

import logging

from freqtrade.constants import Config
from freqtrade.enums import TradingMode
from freqtrade.exceptions import ConfigurationError, OperationalException


logger = logging.getLogger(__name__)

# Internal config key marking that spot-only enforcement is armed for this bot.
SPOT_ONLY_ENFORCED_KEY = "_islamic_spot_only_enforced"


def assert_spot_config(config: Config) -> None:
    """
    L1 check: raise unless the configuration describes pure spot trading.

    :param config: bot configuration mapping.
    :raises ConfigurationError: if ``trading_mode`` is not spot, or any
        ``margin_mode`` is configured.
    """
    trading_mode = config.get("trading_mode", TradingMode.SPOT)
    if TradingMode(trading_mode) != TradingMode.SPOT:
        raise ConfigurationError(
            "Islamic compliance: this platform only supports spot trading. "
            f"trading_mode='{trading_mode}' (margin/futures, leverage, short "
            "selling, funding rates) is forbidden. Set `trading_mode` to 'spot'."
        )
    if config.get("margin_mode"):
        raise ConfigurationError(
            "Islamic compliance: `margin_mode` must not be set on the spot-only "
            f"platform (got '{config['margin_mode']}'). Remove it from the "
            "configuration."
        )


def enforce_spot_only(config: Config) -> None:
    """
    Validate the configuration as pure spot (L1) and arm the enforcement
    marker consumed by exchange-level guards (L2).

    Called from the trading entry point before the bot is constructed.

    :raises ConfigurationError: on any non-spot configuration.
    """
    assert_spot_config(config)
    config[SPOT_ONLY_ENFORCED_KEY] = True
    logger.info(
        "Islamic compliance: spot-only enforcement armed - "
        "margin/futures/leverage operations are blocked for this bot."
    )


def spot_only_enforced(config: Config) -> bool:
    """Return True when spot-only enforcement is armed for this configuration."""
    return bool(config.get(SPOT_ONLY_ENFORCED_KEY))


def assert_spot_operation(config: Config, operation: str) -> None:
    """
    L2 check: block a leverage/margin exchange operation on an armed bot.

    :param config: the exchange's configuration mapping.
    :param operation: human-readable name of the attempted operation (logged).
    :raises OperationalException: if enforcement is armed.
    """
    if spot_only_enforced(config):
        logger.error(
            "Islamic compliance: blocked forbidden exchange operation '%s' "
            "on the spot-only platform.",
            operation,
        )
        raise OperationalException(
            f"Islamic compliance: exchange operation '{operation}' is forbidden "
            "on the spot-only platform."
        )
