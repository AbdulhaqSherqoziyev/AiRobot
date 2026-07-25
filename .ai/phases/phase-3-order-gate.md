# Phase 3 — Pre-order compliance gate + audit (L4 + L6)

Status: done
Started: 2026-07-19   Finished: 2026-07-19

## Goal
An engine-level, strategy-proof check on every entry order (long-only, leverage
1.0, pair not a forbidden instrument) applied just before the order reaches the
exchange; each rejection logged and notified with the reason.

## Reason
ISLAMIC_POLICY.md L4 (per-order gate) + L6 (audit via log + RPC).

## Compliance check
- Touches order placement? **yes** — L4.
- Fail-closed: any non-compliant condition returns a reason ⇒ entry rejected, no
  order sent.
- **Entries only** — hook is inside `execute_entry` before `create_order`; exit and
  stoploss paths are untouched (safety invariant 1).
- Marker-gated: active only when spot-only enforcement is armed
  (`spot_only_enforced`), so library/backtest/upstream-test usage is unaffected —
  consistent with the Phase 1 L2 design.

## Design
- `freqtrade/islamic/order_gate.py`: pure `order_compliance_reason(pair, is_short,
  leverage)` — short ⇒ reject; leverage ≠ 1.0 (±1e-9) ⇒ reject; else
  `screen_pair(pair)` (reuses Phase 2 screening).
- Hook in `freqtradebot.execute_entry` (after stake check, before order): if armed
  and a reason is returned, `logger.warning` + `notify_status(WARNING)` + return
  False. `# noqa: C901` added (method already at the complexity limit; matches
  freqtrade's own convention — upstream logic not restructured, per
  ARCHITECTURE_RULES).

## Audit (L6) — scope decision
Audit = structured WARNING log line (persisted to logfile) + RPC notification
(Telegram/API) with the reason. This matches the L6 policy wording exactly. A
persisted audit *table* (KeyValueStore key list is a strict `Literal`; adding one
widens upstream surface) is deferred to Phase 12 (observability) — recorded here.

## Files affected
- new: `freqtrade/islamic/order_gate.py`
- new: `tests/islamic/test_order_gate.py`, `tests/islamic/test_order_gate_integration.py`
- edited: `freqtrade/islamic/__init__.py` (export), `freqtrade/freqtradebot.py`
  (import + hook + noqa)

## Expected result
With enforcement armed, any short / leverage≠1 / leveraged-token entry is blocked
before the exchange, logged, and surfaced via RPC. Compliant spot longs proceed
normally.

## Risk
Wrongly blocking a legitimate entry. Mitigated: pure function unit-tested; gate is
entries-only; marker-gated so non-platform use is unaffected; upstream execute_entry
tests (incl. futures/short params) still pass unchanged.

## Testing — DONE
- 10 unit tests (`test_order_gate.py`): allow clean long; reject short; reject
  leverage 1.5/2/3/0.5/1.0001; accept within epsilon; reject leveraged tokens.
- 6 integration tests (`test_order_gate_integration.py`): armed bot rejects
  short/leverage/leveraged-token entries (create_order never called); unarmed bot
  does not interfere.
- Regression: `execute_entry` suite 25 passed; full suite 4489 passed, failure set
  == Phase 0 baseline (7 known env failures; the flaky telegram test passed).

## Documentation — DONE
ISLAMIC_POLICY.md (L4 implemented, L6 note), ARCHITECTURE.md §3, ROADMAP status.

## Outcome
Implemented as designed. Deviations recorded: (1) marker-gating added for upstream
compatibility (as in Phase 1); (2) `# noqa: C901` instead of restructuring
execute_entry; (3) persisted audit table deferred to Phase 12 — log + RPC satisfy
L6 now.
