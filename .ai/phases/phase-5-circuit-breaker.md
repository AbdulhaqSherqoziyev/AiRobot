# Phase 5 — Emergency stop & circuit breaker (risk engine)

Status: done
Started: 2026-07-19   Finished: 2026-07-19

## Goal
Automatic circuit breaker that halts all new entries after a losing streak, with
the halt persisting across restarts; plus a documented manual emergency-stop path.

## Reason
Constitution "Risk Management": Emergency Stop + Circuit Breaker.

## Compliance / safety check
- Blocks entries only (global PairLock) — exits and stoplosses never blocked.
- Restart-safe: the lock is a DB `PairLock`, so a triggered breaker persists across
  restarts until it expires or is manually cleared (`/unlock`). Persistence cannot
  brick startup (it is a normal lock row).

## Design
- `freqtrade/plugins/protections/consecutive_loss_guard.py`:
  `ConsecutiveLossGuard(IProtection)` — counts *consecutive* losing trades from the
  most recent within the lookback; when the leading streak reaches `trade_limit`,
  locks all pairs for the configured stop duration. Global stop only.
  Complements upstream `StoplossGuard` (window count of stoploss exits) by reacting
  to a streak regardless of exit reason.
- Manual emergency stop is served by freqtrade's built-in RPC commands `/stop`
  (halt the loop) and `/pause` (stopentry — keep managing open trades, block new
  entries). Both are already exposed on Telegram + API.
- Example config adds `ConsecutiveLossGuard` (4 losses → 24-candle lock).

## Files affected
- new: `freqtrade/plugins/protections/consecutive_loss_guard.py`
- new: `tests/plugins/test_consecutive_loss_guard.py`
- edited: `config_examples/config_islamic_spot.example.json`

## Expected result
Four consecutive losing trades lock all entries for the stop duration (persisted,
restart-safe, RPC PROTECTION_TRIGGER notification via the manager). Manual halt via
`/stop` or `/pause`.

## Risk
Mis-counting the streak. Mitigated: leading-streak-only logic, streak reset on a
recent win, unit-tested matrix; global-only (stop_per_pair returns None).

## Testing — DONE
- 7 tests: below/at streak, streak broken by recent win, only leading losses count,
  no trades, stop_per_pair never locks, loaded via `ProtectionManager`.
- Regression: full suite (see phase-5 log) clean vs baseline; example config with the
  extended protection stack validates.

## Documentation — DONE
ROADMAP status; ARCHITECTURE.md §3 protections list; this record.

## Outcome
Delivered the automatic circuit breaker as a self-contained protection (no upstream
RPC-command surface). A *dedicated persisted emergency-stop command* (a new
Telegram/API command surviving restart beyond `/stop`) was intentionally NOT added
to avoid broad edits to `telegram.py`/`api_server`; built-in `/stop`+`/pause` cover
the manual case. A richer persisted kill-switch command is a candidate for a later
RPC-focused phase — recorded here.
