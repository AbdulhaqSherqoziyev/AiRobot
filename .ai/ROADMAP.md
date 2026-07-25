# Roadmap — Phased Implementation Plan

> One phase in flight at a time (see [PROJECT_RULES.md](PROJECT_RULES.md)).
> Every phase gets a filled [TASK_TEMPLATE.md](TASK_TEMPLATE.md) in `.ai/phases/`
> before implementation starts. Status values: `planned | in-progress | done | dropped`.
>
> Phases are intentionally small. Later phases are sketched at lower resolution and
> must be re-planned in detail when they come up — do not implement from this file alone.

## Stage A — Foundation & Compliance Hardening

### Phase 0 — Baseline verification — `done`
- **Goal:** Reproducible dev environment; upstream test suite green locally; record the
  exact baseline (Python version, deps, test results) in `.ai/phases/phase-0.md`.
- **Reason:** All later "our change broke it" questions need a trusted baseline.
- **Files affected:** none (environment only; possibly `.ai/` records).
- **Expected result:** `pytest` green (or documented pre-existing failures), ruff clean,
  dry-run bot starts with a sample spot config.
- **Risk:** none to code. Time risk if upstream dev branch has flaky tests — record them.
- **Rollback:** n/a (no code change).
- **Testing:** full `pytest -n auto`; `freqtrade trade --dry-run` smoke test.
- **Docs:** baseline record in `.ai/phases/phase-0.md`.

### Phase 1 — Spot-only hard guard (compliance L1+L2) — `done`
- **Goal:** Make non-SPOT operation impossible by construction: config validation
  rejects `trading_mode != spot` / any `margin_mode`; an exchange-level guard asserts
  SPOT at `Exchange.__init__` and refuses leverage/margin calls.
- **Reason:** ISLAMIC_POLICY.md L1/L2 — config alone is not assurance.
- **Files affected:** new `freqtrade/islamic/` package (guard module);
  `configuration/config_validation.py` (one added `_validate_*` hook);
  `exchange/exchange.py` (minimal hook in `__init__`/`_lev_prep`); tests.
- **Expected result:** starting the bot with futures/margin config fails at startup with
  a clear message; `_set_leverage`/`set_margin_mode` raise if ever reached.
- **Risk:** breaking backtesting/hyperopt for spot configs (they share config path).
  Mitigate: run optimize-mode tests; guard keyed to all runmodes but spot-only.
- **Rollback:** the guard is a small isolated module + two hook lines — revert commit.
- **Testing:** unit tests for accept/reject matrices (spot ok; margin/futures/leverage
  rejected; guard exception ⇒ startup abort); full suite regression.
- **Docs:** ARCHITECTURE.md §4, ISLAMIC_POLICY.md enforcement table, ADR-0002.

### Phase 2 — Haram-instrument pairlist filter (compliance L5) — `done`
- **Goal:** `IslamicComplianceFilter` pairlist filter: removes leveraged tokens
  (pattern-based: UP/DOWN, 3L/3S, BULL/BEAR, etc.) and assets on a configurable
  compliance blacklist.
- **Reason:** Screen the universe before signals exist (ISLAMIC_POLICY.md L5).
- **Files affected:** new `freqtrade/plugins/pairlist/IslamicComplianceFilter.py` (or
  `user_data/`-loaded — decide via ADR), `config_schema` addition, tests, sample config.
- **Expected result:** filtered pairs never enter the whitelist; each removal logged
  with reason once per refresh.
- **Risk:** false positives removing legitimate pairs (e.g. tokens whose name matches a
  pattern). Mitigate: allowlist override + log-only "audit mode" first.
- **Rollback:** remove filter entry from config; delete module.
- **Testing:** unit tests with synthetic markets incl. edge-case tickers; integration
  test via `PairListManager`.
- **Docs:** ARCHITECTURE.md §13, config guide entry, ISLAMIC_POLICY.md table.

### Phase 3 — Pre-order compliance gate + audit trail (L4+L6) — `done`
- **Goal:** Engine-level pre-order validation (long-only, leverage==1.0, pair passes
  screening, spot market) that cannot be overridden by a strategy; every rejection
  logged + persisted (KeyValueStore/CustomData) + emitted as a new
  `RPCMessageType.COMPLIANCE_REJECT` style message.
- **Reason:** Defense in depth; auditability ("logs explain WHY").
- **Files affected:** `freqtrade/islamic/` gate module; minimal hook in
  `freqtradebot.execute_entry` near the `confirm_trade_entry` call
  (`freqtradebot.py:932`); `enums/rpcmessagetype.py`, `rpc/rpc_types.py`, telegram/
  webhook rendering; tests.
- **Expected result:** any non-compliant order attempt is blocked pre-exchange and
  visible in Telegram/API with reason.
- **Risk:** blocking legitimate exits if mis-hooked. Mitigate: gate applies to
  **entries only** (ARCHITECTURE_RULES.md safety invariant 1).
- **Rollback:** remove hook line; module is inert without it.
- **Testing:** entry blocked/allowed matrices; exit paths untouched (regression tests on
  exit flow); RPC message rendering tests.
- **Docs:** ARCHITECTURE.md §3/§13, ISLAMIC_POLICY.md, ADR.

## Stage B — Risk Engine

### Phase 4 — Risk limits via protections (daily/weekly loss, drawdown) — `done`
- **Goal:** Implement `MaxDailyLoss` and `MaxWeeklyLoss` protections (custom
  `IProtection` subclasses) complementing upstream `MaxDrawdown`; config-driven,
  global locks.
- **Reason:** Constitution requires max daily/weekly loss and drawdown limits.
- **Files affected:** new protection modules (resolver-loaded), config schema/docs,
  tests.
- **Expected result:** breaching a limit locks all entries for the configured window,
  with notification.
- **Risk:** mis-computed realized PnL windows (timezones, open trades). Mitigate: use
  upstream trade query helpers; UTC-only; tests with fixture trades.
- **Rollback:** remove from `protections` config.
- **Testing:** unit tests on lock triggering windows/thresholds; behavior across
  restarts (locks persist via PairLock table).
- **Docs:** config guide; ARCHITECTURE.md §3 protections list.

### Phase 5 — Emergency stop & circuit breaker — `done`
- **Goal:** A kill-switch: one command (Telegram/API) + automatic trigger conditions
  (e.g. N consecutive losses, exchange error storm) that pause entries and optionally
  close positions; state persisted so restarts stay stopped.
- **Reason:** Constitution: Emergency Stop + Circuit Breaker; upstream has
  `/stop`+`/pause` and protections — this phase composes and persists them.
- **Files affected:** `freqtrade/islamic/` or `plugins/` module, RPC command wiring,
  KeyValueStore state, tests.
- **Expected result:** single action halts entries platform-wide, survives restart,
  clearly reported.
- **Risk:** must never block exits; persistence of stop state must not brick startup.
  Mitigate: entries-only gating; explicit unlock command.
- **Rollback:** feature flag off in config.
- **Testing:** trigger/untrigger, restart persistence, exit-still-works tests.
- **Docs:** runbook entry (new OPERATIONS doc), config guide.

### Phase 6 — Position sizing & exposure limits — `planned`
- **Goal:** Enforce max position size (per pair and % of capital), max total exposure,
  and trade cooldown defaults; conservative defaults in a shipped sample config.
- **Reason:** Constitution risk requirements; capital preservation first.
- **Files affected:** `custom_stake_amount`-level guard or wallet-level check, sample
  config `config_examples/`, tests.
- **Expected result:** stakes are capped regardless of strategy requests.
- **Risk:** interaction with position adjustment (DCA) paths — cap must count
  adjustments. Mitigate: tests over `adjust_trade_position` flow.
- **Rollback:** config flag.
- **Testing:** sizing matrices incl. DCA; dry-run verification.
- **Docs:** config guide; ARCHITECTURE.md.

## Stage C — AI Advisor Layer

### Phase 7 — AI recommendation pipeline design (ADR, no code) — `planned`
- **Goal:** Decide, in an ADR: how FreqAI predictions (and/or an external advisor)
  become `TradeRecommendation` objects; confidence-threshold model; how the four
  validations (market/risk/Islamic/confidence) compose; long-only feature/target
  design; RL short-action exclusion.
- **Reason:** "AI recommends, engine executes" needs a designed contract before code.
- **Files affected:** `.ai/DECISIONS.md`, `.ai/ARCHITECTURE.md` only.
- **Expected result:** accepted ADR with interfaces and data flow.
- **Risk:** none (design only).
- **Rollback:** supersede the ADR.
- **Testing:** n/a; design review against REVIEW_CHECKLIST.
- **Docs:** this is docs.

### Phase 8 — Baseline halal FreqAI strategy (dry-run only) — `planned`
- **Goal:** A reference long-only FreqAI strategy implementing the Phase 7 contract:
  feature engineering, confidence gating in `confirm_trade_entry`, full logging of
  every recommendation and decision.
- **Reason:** Prove the AI pipeline end-to-end in dry-run before any live use.
- **Files affected:** `user_data/strategies/`, freqai config example, tests
  (backtest-based), docs.
- **Expected result:** backtests + dry-run runs with complete decision audit trail.
- **Risk:** lookahead bias. Mitigate: run `optimize/analysis` lookahead & recursive
  tools as an acceptance gate.
- **Rollback:** strategy file removal; no core changes.
- **Testing:** backtest determinism test, lookahead analysis clean, unit tests for
  gating logic.
- **Docs:** strategy guide in `.ai/` + user docs.

### Phase 9 — AI decision notifications & reporting — `planned`
- **Goal:** Telegram/API surfaces: recommendation issued/accepted/rejected (+why),
  daily/weekly/monthly summaries including compliance and risk events.
- **Reason:** Constitution telegram & logging requirements.
- **Files affected:** `RPCMessageType` additions, telegram/webhook/api rendering,
  tests.
- **Expected result:** operator sees every AI decision and rejection reason.
- **Risk:** message spam. Mitigate: batching/config verbosity levels.
- **Rollback:** message types config-gated.
- **Testing:** rendering unit tests per channel.
- **Docs:** telegram usage doc.

## Stage D — Production Hardening (each item becomes its own small phase when reached)

- **Phase 10 — Operations runbook & deployment:** docker compose profile for the
  platform, systemd notes, backup/restore of DB + FreqAI models, upgrade procedure.
- **Phase 11 — Security pass:** secrets handling audit, API server exposure review
  (JWT/ws_token config), dependency audit, least-privilege exchange API keys
  (spot-only, no-withdrawal) documented and verified at startup.
- **Phase 12 — Observability:** structured decision log (queryable audit table),
  health metrics, optional external monitoring hook.
- **Phase 13 — Upstream sync process:** documented merge cadence + conflict playbook
  for our hook points.
- **Phase 14 — Live pilot:** tiny-capital live run behind all guards; exit criteria
  defined in advance; post-mortem doc.

## Sequencing rules

- Stage A must complete before any Stage C work runs even in dry-run.
- Phase 14 (live) requires Stages A, B, D-security complete and owner sign-off.
- Any phase may be split further at planning time; never merged together.
