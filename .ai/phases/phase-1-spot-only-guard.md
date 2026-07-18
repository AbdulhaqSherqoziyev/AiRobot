# Phase 1 — Spot-only hard guard (compliance L1+L2)

Status: done
Started: 2026-07-19   Finished: 2026-07-19

## Goal
Non-SPOT operation becomes impossible by construction: startup aborts on any
non-spot configuration, and the exchange layer refuses leverage/margin operations
even if reached through an unforeseen path.

## Reason
ISLAMIC_POLICY.md layers L1 (config) and L2 (exchange). Upstream SPOT behavior is
correct but only config-gated (see ADR-0002).

## Compliance check (mandatory)
- Touches order placement / leverage / shorting / pair selection / funding? **yes**
- Layers: implements L1+L2. Fail-closed: guard raises typed exceptions ⇒ bot never
  starts / order never placed. Entries-vs-exits: guard acts at startup and at
  leverage/margin call sites only — it cannot block exits of existing spot positions.
- Uncertainty: none — spot-only is the constitution's explicit core rule.

## Design
New package `freqtrade/islamic/` (first-party platform code, per ADR-0001):

- `islamic/__init__.py`, `islamic/compliance.py`:
  - `assert_spot_config(config)` — raises `ConfigurationError` unless
    `trading_mode` is `spot` (or unset ⇒ defaults to spot) and `margin_mode` is empty.
  - `assert_spot_order_context(trading_mode, leverage)` — raises `OperationalException`
    if mode != SPOT or leverage != 1.0.
- Hook 1 (L1): one `_validate_*` call added in
  `configuration/config_validation.py::validate_config_consistency`.
- Hook 2 (L2): assertion at the end of `Exchange.__init__` mode resolution
  (`exchange/exchange.py:208-217` region) + guard at `_lev_prep`
  (`exchange.py:1408`) so `set_margin_mode`/`_set_leverage` are unreachable.
- Hooks are 1–2 lines each, commented with a `# Islamic platform guard` marker for
  upstream-merge visibility (Phase 13 inventory).
- Config surface: none new (guard is unconditional — this platform is spot-only by
  identity, not by option).

Alternative considered: config-only enforcement (rejected — ADR-0002); monkey-patching
from user_data (rejected — fragile, invisible to reviewers).

## Files affected
- new: `freqtrade/islamic/__init__.py`, `freqtrade/islamic/compliance.py`
- new: `tests/islamic/test_compliance.py`
- upstream hooks: `freqtrade/configuration/config_validation.py`,
  `freqtrade/exchange/exchange.py` (2 sites)

## Expected result
- `freqtrade trade`/`backtesting` etc. with `trading_mode: futures|margin` (or any
  `margin_mode`) aborts with a clear compliance message.
- Any runtime path calling `_lev_prep` with leverage ≠ 1.0, or
  `_set_leverage`/`set_margin_mode`, raises before any exchange call.
- Spot configs behave byte-for-byte as before (regression suite green).

## Risk
- Upstream tests that exercise futures/margin modes will hit the guard when run
  against the shared code — guard must key on runtime config, and upstream tests
  construct futures configs intentionally. **Mitigation:** hooks raise only in
  execution paths, and the test impact is assessed in implementation; if upstream
  futures tests break en masse, scope the L1 hook to trade/dry-run runmodes via an
  explicit decision recorded here (utility/backtest analysis of futures data is not
  order placement). Fallback decision to be made with evidence, not assumption.

## Rollback plan
Revert the single commit: hooks are 3 lines total; module is inert without them.

## Testing requirements
- Unit: accept/reject matrix for `assert_spot_config` (spot/unset/margin/futures/
  margin_mode combinations); `assert_spot_order_context` incl. leverage 1.0 vs ≠1.0;
  exception types.
- Integration: bot startup with futures config aborts; spot dry-run startup OK.
- Regression: full `pytest -n auto`; delta vs Phase 0 baseline must be zero except
  intentionally-guarded cases (each listed here).

## Documentation updates
ARCHITECTURE.md §4 (guard locations), ISLAMIC_POLICY.md table (L1/L2 → implemented),
ROADMAP status, ADR-0002 already covers rationale.

## Review
- [ ] REVIEW_CHECKLIST.md passed

## Outcome
Implemented as designed, with one evidence-driven refinement: upstream tests use
futures/margin heavily (77 parametrized short-tests and dozens of futures test
files), so hard guards in `Exchange.__init__`/`validate_config_consistency` would
have broken hundreds of upstream tests. Instead:

- L1 lives at the trading entry point (`Worker._init` — covers live AND dry-run
  `freqtrade trade`), raising `ConfigurationError` on any non-spot config.
- The enforcement marker travels with the bot's config mapping
  (`SPOT_ONLY_ENFORCED_KEY`), not process-global state — library/backtest/test
  usage stays upstream-compatible while an armed bot's exchange refuses
  `_set_leverage`/`set_margin_mode` (guard placed BEFORE the dry-run early-return).

Evidence:
- 15 new tests in `tests/islamic/test_compliance.py` (accept/reject matrices,
  armed-exchange refusal, Worker abort/arm integration) — all pass.
- Full regression: 4431 passed; failure set identical to Phase 0 baseline
  (8 known environment failures). Two extra failures found during the run were
  missing-file artifacts of overly-broad gitignore patterns in the initial import
  (fixed in commit f3bdff7, unrelated to this phase's code).
- CLI verification: futures config aborts with the compliance message; spot config
  logs "spot-only enforcement armed" and reaches RUNNING heartbeat.

Note: `validate_config_consistency` hook from the original design was NOT needed —
Worker-level enforcement subsumes it for the trading path. Recorded here as a
conscious deviation.
