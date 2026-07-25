"""
Startup security-posture validation (defense in depth).

Enforces basic security hygiene at the trading entry point so the platform cannot
start in an obviously unsafe configuration:

* live trading must have real exchange credentials present (supplied via env vars);
* an API server exposed on a non-loopback address must be protected by a strong
  JWT secret and non-trivial credentials.

Exchange-side key-permission checks (no withdrawal rights, spot-only) depend on
per-exchange APIs and are covered by the operational security checklist
(`.ai/SECURITY_CHECKLIST.md`); this module performs the exchange-agnostic,
deterministic checks. Fails closed.
"""

import logging

from freqtrade.constants import Config
from freqtrade.exceptions import ConfigurationError


logger = logging.getLogger(__name__)

_LOCAL_ADDRESSES = frozenset({"127.0.0.1", "localhost", "::1"})
_MIN_JWT_SECRET_LEN = 16
_WEAK_PASSWORDS = frozenset({"", "password", "admin", "changeme", "freqtrader", "1234"})


def validate_security_config(config: Config) -> None:
    """
    Enforce minimum security hygiene on the configuration.

    :raises ConfigurationError: on missing live credentials or an unsafely-exposed
        API server.
    """
    if not config.get("dry_run", True):
        exchange = config.get("exchange", {})
        if not exchange.get("key") or not exchange.get("secret"):
            raise ConfigurationError(
                "Security: live trading requires exchange API key and secret "
                "(supply them via environment variables, not the config file)."
            )

    api = config.get("api_server", {})
    if api.get("enabled"):
        listen_ip = str(api.get("listen_ip_address", "127.0.0.1"))
        if listen_ip not in _LOCAL_ADDRESSES:
            jwt_secret = api.get("jwt_secret_key") or ""
            if len(jwt_secret) < _MIN_JWT_SECRET_LEN:
                raise ConfigurationError(
                    "Security: the API server is exposed on a non-local address "
                    f"({listen_ip}) and requires a strong `jwt_secret_key` "
                    f"(>= {_MIN_JWT_SECRET_LEN} characters)."
                )
            if not api.get("username") or api.get("password", "") in _WEAK_PASSWORDS:
                raise ConfigurationError(
                    "Security: the API server is exposed on a non-local address "
                    f"({listen_ip}) and requires a username and a strong password."
                )

    logger.info("Security posture validated.")
