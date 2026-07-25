# Phase 2 — Haram-instrument pairlist filter (compliance L5)

Status: done
Started: 2026-07-19   Finished: 2026-07-19

## Goal
Remove Sharia-non-compliant instruments (leveraged tokens + blacklisted assets)
from the tradable universe before any signal is generated.

## Reason
ISLAMIC_POLICY.md layer L5 — screen the pair universe up front.

## Compliance check
- Touches pair selection? **yes** — implements L5.
- Fail-closed: unknown/borderline tickers are removed (better to skip a pair than
  trade a haram one). Allowlist + audit-mode give safe rollout controls.
- Entries-only: filtering the whitelist never blocks exits of existing positions.

## Design (see ADR-0005)
- `freqtrade/islamic/screening.py`: pure functions — `base_currency`,
  `leveraged_token_reason` (suffixes UP/DOWN/BULL/BEAR + multiplier `\d+[LS]`,
  with a min-underlying-length guard against false positives like `JUP`),
  `screen_pair` (allowlist > blacklist > leveraged detection).
- `freqtrade/plugins/pairlist/IslamicComplianceFilter.py`: thin `IPairList`
  adapter; config keys `blacklist`, `allowlist`, `leverage_suffixes`,
  `audit_mode`; logs every rejection with reason via `log_once`.
- `freqtrade/constants.py`: one added line registering the name in
  `AVAILABLE_PAIRLISTS` (schema enum). Marked hook.
- `config_examples/config_islamic_spot.example.json`: canonical spot config
  demonstrating `VolumePairList → IslamicComplianceFilter → AgeFilter → PriceFilter`.

## Files affected
- new: `freqtrade/islamic/screening.py`
- new: `freqtrade/plugins/pairlist/IslamicComplianceFilter.py`
- new: `tests/islamic/test_screening.py`, `tests/islamic/test_compliance_filter.py`
- new: `config_examples/config_islamic_spot.example.json`
- edited: `freqtrade/islamic/__init__.py` (exports), `freqtrade/constants.py` (enum)

## Expected result
Leveraged tokens (`BTCUP`, `BTCDOWN`, `ETH3L`, `SOLBULL` …) and blacklisted assets
never enter the whitelist; each removal logged once per refresh. Legit short
tickers (`JUP`) survive.

## Risk
False positives removing legit pairs. Mitigated: min-underlying-length heuristic,
`allowlist` override, and `audit_mode` (log-only) for safe rollout.

## Rollback plan
Remove the filter entry from config; revert the commit (module is additive; only
the one-line enum edit touches upstream).

## Testing requirements — DONE
- 22 unit tests (`test_screening.py`): detection matrix, false-positive guards,
  blacklist/allowlist precedence, custom suffixes.
- 9 integration tests (`test_compliance_filter.py`): loaded via real
  `PairListResolver`, filter removes leveraged tokens / keeps clean, audit mode,
  blacklist, allowlist, custom suffixes, short_desc.
- Regression: `tests/plugins/test_pairlist.py` 314 passed. Example config validates
  clean (`show-config` rc=0).

## Documentation updates — DONE
ISLAMIC_POLICY.md (L5 implemented), ARCHITECTURE.md §13, ROADMAP status, ADR-0005.

## Outcome
Implemented as designed. One expected upstream touch discovered during
verification: the config schema validates `pairlists[].method` against the
`AVAILABLE_PAIRLISTS` enum, so the filter name had to be registered there (one
additive line) — recorded in ADR-0005 and the merge-hook inventory.
