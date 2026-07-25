# Phase 4 — Risk limits: daily/weekly max loss (risk engine)

Status: done
Started: 2026-07-19   Finished: 2026-07-19

## Goal
Hard calendar-period loss budgets: stop all entries when realized loss in the
current day or week reaches a configured fraction of the starting balance; unlock
automatically when the period rolls over.

## Reason
Constitution "Risk Management": Maximum Daily Loss + Maximum Weekly Loss. Capital
preservation is priority #1.

## Compliance / safety check
- Touches order placement? Indirectly — blocks *entries* via a global pair lock.
  Exits and stoplosses are never blocked (protections gate entries only).
- Fail-safe: inert unless explicitly configured (`max_allowed_loss > 0`) and a
  positive starting balance is known.

## Design
- `freqtrade/plugins/protections/max_loss_protection.py`:
  - `_MaxLossProtection(IProtection)` shared base — global stop only; sums
    `close_profit_abs` of trades closed since the period start; if the net is a
    loss ≥ `max_allowed_loss` × starting_balance, locks all pairs until period end.
  - `MaxDailyLoss` — period = calendar day (00:00 UTC → next 00:00).
  - `MaxWeeklyLoss` — period = calendar week (Monday 00:00 UTC → next Monday).
- Calendar-based (not rolling window) so each day/week gets a fresh budget —
  complements upstream `MaxDrawdown` (rolling) and `StoplossGuard`.
- No schema edit needed: protections are not enum-validated; the
  `ProtectionResolver` discovers the classes by file.
- `config_examples/config_islamic_spot.example.json` now ships a conservative
  protection stack: MaxDailyLoss 5%, MaxWeeklyLoss 10%, MaxDrawdown, StoplossGuard,
  CooldownPeriod.

## Files affected
- new: `freqtrade/plugins/protections/max_loss_protection.py`
- new: `tests/plugins/test_max_loss_protection.py`
- edited: `config_examples/config_islamic_spot.example.json` (protections stack)

## Expected result
Reaching the daily/weekly loss budget locks all entries (with a logged reason and
RPC PROTECTION_TRIGGER message via the manager) until the period rolls over.

## Risk
Mis-computed period boundaries or PnL. Mitigated: UTC-only, explicit period-bounds
unit tests, mocked-trade threshold matrix; `stop_per_pair` always None (global only).

## Testing — DONE
- 12 tests: daily/weekly period bounds; no-lock (no trades / net profit / below
  threshold / unconfigured / zero balance); lock at threshold with correct `until`;
  weekly unlock next Monday; stop_per_pair never locks; both loaded via
  `ProtectionManager` (resolver discovery).
- Regression: `tests/plugins/test_protections.py` 51 passed. Example config with
  the full protection stack validates clean.

## Documentation — DONE
ROADMAP status; ARCHITECTURE.md §3 protections list; this record.

## Outcome
Implemented as designed. Chose calendar-period semantics over a rolling window for
daily/weekly budgets (more meaningful risk reset); documented. Emergency stop and
circuit breaker are Phase 5; position sizing is Phase 6.
