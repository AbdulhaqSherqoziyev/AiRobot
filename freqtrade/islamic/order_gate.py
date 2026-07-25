"""
Pre-order Sharia-compliance gate (`.ai/ISLAMIC_POLICY.md` layer L4).

The final, engine-level check applied to every entry order just before it reaches
the exchange. It cannot be overridden by a strategy and complements the earlier
layers (L1/L2 spot-only, L5 pair screening) with a per-order assertion:

* long only (no short selling),
* leverage exactly 1.0,
* the pair is not a forbidden instrument (leveraged token / blacklisted).

Pure and side-effect free so it is fully unit-testable; the caller
(``FreqtradeBot.execute_entry``) is responsible for logging, notifying (L6) and
rejecting the entry when a reason is returned. Applied to entries only — it never
touches exit or stoploss paths.
"""

from freqtrade.islamic.screening import screen_pair


# Leverage is a float; compare against 1.0 with a tolerance.
_LEVERAGE_EPSILON = 1e-9


def order_compliance_reason(pair: str, is_short: bool, leverage: float) -> str | None:
    """
    Return a human-readable rejection reason if an entry order is
    Sharia-non-compliant, otherwise ``None``.

    :param pair: the pair being entered.
    :param is_short: whether the entry is a short (always forbidden).
    :param leverage: the leverage for the order (must be 1.0).
    """
    if is_short:
        return "short selling is forbidden"
    if abs(leverage - 1.0) > _LEVERAGE_EPSILON:
        return f"leverage {leverage:g} is forbidden (must be 1.0)"
    return screen_pair(pair)
