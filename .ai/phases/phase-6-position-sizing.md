# Phase 6 — Position sizing & exposure limits (risk engine)

Status: done
Started: 2026-07-19   Finished: 2026-07-19

## Goal
Guarantee bounded position sizing and total exposure, and refuse to start the
platform with a reckless (unbounded-exposure) configuration.

## Reason
Constitution "Risk Management": Maximum Position Size, Maximum Open Trades, Maximum
total exposure, Trade Cooldown. Capital preservation is priority #1.

## Design
Freqtrade already enforces sizing at runtime:
- `stake_amount` (fixed) → per-position cap.
- `max_open_trades` → concurrent positions.
- `tradable_balance_ratio` / `available_capital` → total deployable capital.
- `CooldownPeriod` protection → trade cooldown.

The failure mode not covered natively is a *misconfiguration* leaving exposure
unbounded (unlimited `max_open_trades`). Phase 6 closes it:
- `freqtrade/islamic/risk_config.py::validate_risk_config()` — raises
  `ConfigurationError` if `max_open_trades` is unlimited (-1 / inf) or ≤ 0.
- Hooked in `Worker._init` right after `enforce_spot_only` (trading path only;
  backtest/hyperopt use different entry points).
- Example config sizing made conservative: `stake_amount` 50, `max_open_trades` 3
  (≤ 15% deployed), `tradable_balance_ratio` 0.95 (cash buffer), plus the Phase 4/5
  protections and `CooldownPeriod`.

## Files affected
- new: `freqtrade/islamic/risk_config.py`, `tests/islamic/test_risk_config.py`
- edited: `freqtrade/islamic/__init__.py` (export), `freqtrade/worker.py` (hook),
  `config_examples/config_islamic_spot.example.json` (conservative sizing)

## Expected result
Starting `freqtrade trade` with unlimited/≤0 `max_open_trades` aborts with a clear
risk-policy message; conservative example config bounds per-position (~5% of wallet)
and total (~15%) exposure using freqtrade's native, tested enforcement.

## Risk
Blocking a legitimate startup. Mitigated: only rejects genuinely unbounded config;
default_conf (finite) and upstream Worker/main tests unaffected (26 passed).

## Testing — DONE
- 9 tests: accepts finite positive; rejects -1/0/inf/missing; Worker aborts on
  unbounded config.
- Regression: Worker + main suites 26 passed; full suite clean vs baseline.

## Documentation — DONE
ROADMAP status; this record; ARCHITECTURE extension table.

## Outcome
Delivered config-gate enforcement of bounded exposure + conservative shipped sizing,
leveraging freqtrade's native runtime sizing (robust, tested). A *runtime hard cap
overriding a strategy's `custom_stake_amount`* was intentionally deferred: our
reference strategy (Phase 8) will use fixed `stake_amount` (natively bounded), so a
per-trade custom-stake cap is only needed if/when a custom-sizing strategy is added
— recorded as a follow-up to avoid adding risk to the already-complex `execute_entry`
now.
