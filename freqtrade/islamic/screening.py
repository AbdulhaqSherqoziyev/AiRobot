"""
Instrument screening for Sharia compliance (`.ai/ISLAMIC_POLICY.md` layer L5).

Pure, side-effect-free helpers that decide whether a trading pair describes a
forbidden instrument. Kept separate from the pairlist adapter so the logic can be
unit-tested in isolation and reused by other guards (e.g. the pre-order gate).

Currently screens for **leveraged tokens** (e.g. ``BTCUP``/``BTCDOWN``,
``BTC3L``/``BTC3S``, ``ETHBULL``/``ETHBEAR``) which embed leverage and are haram,
plus a caller-supplied blacklist of specific assets/pairs.
"""

import re


# Directional suffixes used by leveraged tokens (checked on the base currency).
DEFAULT_LEVERAGED_SUFFIXES: tuple[str, ...] = ("UP", "DOWN", "BULL", "BEAR")

# Leveraged multiplier tokens: an underlying followed by a multiplier and a
# direction, e.g. ``BTC3L`` (3x long), ``ETH3S`` (3x short), ``SOL5L``.
_MULTIPLIER_RE = re.compile(r"^(?P<underlying>[A-Z0-9]+?)(?P<mult>\d+)(?P<dir>[LS])$")

# Minimum length of the remaining underlying symbol required before a suffix or
# multiplier match is treated as a leveraged token. Protects short legitimate
# tickers whose name merely ends in a suffix (e.g. ``JUP`` ends in "UP", leaving
# only "J").
DEFAULT_MIN_UNDERLYING_LEN = 2


def base_currency(pair: str) -> str:
    """Return the upper-cased base currency of a ``BASE/QUOTE`` pair."""
    return pair.split("/")[0].strip().upper()


def leveraged_token_reason(
    base: str,
    suffixes: tuple[str, ...] = DEFAULT_LEVERAGED_SUFFIXES,
    min_underlying_len: int = DEFAULT_MIN_UNDERLYING_LEN,
) -> str | None:
    """
    Return a human-readable reason if ``base`` looks like a leveraged token,
    otherwise ``None``.

    :param base: upper-cased base currency (e.g. ``"BTCUP"``).
    :param suffixes: directional suffixes to detect.
    :param min_underlying_len: minimum remaining underlying length required for a
        match, guarding against false positives on short tickers.
    """
    for suffix in suffixes:
        if base.endswith(suffix) and len(base) - len(suffix) >= min_underlying_len:
            return f"leveraged token (suffix '{suffix}')"

    match = _MULTIPLIER_RE.match(base)
    if match and len(match.group("underlying")) >= min_underlying_len:
        return f"leveraged token (multiplier '{match.group('mult')}{match.group('dir')}')"

    return None


def screen_pair(
    pair: str,
    *,
    blacklist: frozenset[str] = frozenset(),
    allowlist: frozenset[str] = frozenset(),
    suffixes: tuple[str, ...] = DEFAULT_LEVERAGED_SUFFIXES,
    min_underlying_len: int = DEFAULT_MIN_UNDERLYING_LEN,
) -> str | None:
    """
    Screen a single pair for Sharia compliance.

    :param pair: ``BASE/QUOTE`` pair.
    :param blacklist: upper-cased bases or full pairs that are always forbidden.
    :param allowlist: upper-cased bases or full pairs that bypass every check
        (false-positive override); takes precedence over all other rules.
    :param suffixes: leveraged-token suffixes to detect.
    :param min_underlying_len: see :func:`leveraged_token_reason`.
    :return: a rejection reason string if the pair is non-compliant, else ``None``.
    """
    pair_u = pair.strip().upper()
    base = base_currency(pair)

    if pair_u in allowlist or base in allowlist:
        return None

    if pair_u in blacklist or base in blacklist:
        return "compliance blacklist"

    return leveraged_token_reason(base, suffixes, min_underlying_len)
