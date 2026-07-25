"""
Islamic compliance pair list filter (Sharia screening, `.ai/ISLAMIC_POLICY.md` L5).

Removes forbidden instruments from the whitelist before any trading signal is
considered: leveraged tokens (``BTCUP``, ``BTC3L``, ``ETHBULL`` …) and any asset
on a configurable compliance blacklist. Screening logic lives in
``freqtrade.islamic.screening`` and is unit-tested there.
"""

import logging

from freqtrade.constants import Config
from freqtrade.exchange.exchange_types import Ticker
from freqtrade.islamic.screening import DEFAULT_LEVERAGED_SUFFIXES, screen_pair
from freqtrade.plugins.pairlist.IPairList import IPairList, PairlistParameter, SupportsBacktesting


logger = logging.getLogger(__name__)


class IslamicComplianceFilter(IPairList):
    """
    Pairlist filter that drops Sharia-non-compliant instruments.

    Configuration (all optional) in the ``pairlists`` entry:

    * ``blacklist``: extra base assets or full pairs that are always removed.
    * ``allowlist``: base assets or full pairs that bypass screening
      (false-positive override).
    * ``leverage_suffixes``: override the default leveraged-token suffixes.
    * ``audit_mode``: if true, log rejections but keep the pairs (dry evaluation
      before enforcing). Defaults to false (pairs are removed).
    """

    supports_backtesting = SupportsBacktesting.YES

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        cfg: Config = self._pairlistconfig
        self._blacklist = frozenset(a.strip().upper() for a in cfg.get("blacklist", []))
        self._allowlist = frozenset(a.strip().upper() for a in cfg.get("allowlist", []))
        suffixes = cfg.get("leverage_suffixes")
        self._suffixes = (
            tuple(s.strip().upper() for s in suffixes) if suffixes else DEFAULT_LEVERAGED_SUFFIXES
        )
        self._audit_mode = bool(cfg.get("audit_mode", False))

    @property
    def needstickers(self) -> bool:
        """Screening uses only pair names; no tickers required."""
        return False

    def short_desc(self) -> str:
        mode = " (audit mode)" if self._audit_mode else ""
        return f"{self.name} - Removing Sharia-non-compliant instruments{mode}."

    @staticmethod
    def description() -> str:
        return "Removes leveraged tokens and blacklisted assets (Sharia compliance)."

    @staticmethod
    def available_parameters() -> dict[str, PairlistParameter]:
        return {
            "blacklist": {
                "type": "list",
                "default": [],
                "description": "Compliance blacklist",
                "help": "Base assets or pairs that are always removed.",
            },
            "allowlist": {
                "type": "list",
                "default": [],
                "description": "Compliance allowlist",
                "help": "Base assets or pairs that bypass screening (false-positive override).",
            },
            "leverage_suffixes": {
                "type": "list",
                "default": list(DEFAULT_LEVERAGED_SUFFIXES),
                "description": "Leveraged-token suffixes",
                "help": "Directional suffixes identifying leveraged tokens.",
            },
            "audit_mode": {
                "type": "boolean",
                "default": False,
                "description": "Audit mode",
                "help": "If true, log rejections but keep pairs instead of removing them.",
            },
        }

    def _validate_pair(self, pair: str, ticker: Ticker | None) -> bool:
        """
        :param pair: pair to screen.
        :param ticker: unused (screening is name-based).
        :return: True to keep the pair, False to remove it. In audit mode always
            returns True, but still logs any rejection reason.
        """
        reason = screen_pair(
            pair,
            blacklist=self._blacklist,
            allowlist=self._allowlist,
            suffixes=self._suffixes,
        )
        if reason is None:
            return True

        if self._audit_mode:
            self.log_once(
                f"Islamic compliance (audit): {pair} would be removed - {reason}.",
                logger.info,
            )
            return True

        self.log_once(
            f"Islamic compliance: removing {pair} from whitelist - {reason}.",
            logger.info,
        )
        return False
