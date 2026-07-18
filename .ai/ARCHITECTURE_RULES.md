# Architecture Rules — How We Are Allowed to Change This System

> Companion to [ARCHITECTURE.md](ARCHITECTURE.md) (how it *is*). This file states how it
> *may evolve*. Violations are review blockers.

## 1. Prime directive: extend, don't fork

This repo tracks upstream Freqtrade (`2026.7-dev`). Upstream ships fixes for exchange
API changes constantly; losing merge-ability is an existential maintenance risk.

- **Prefer, in order:** `user_data/` resolver-loaded classes → new modules in a
  dedicated package (`freqtrade/islamic/` once created) → minimal, surgical hooks in
  core files → (last resort, with ADR) core modification.
- Any edit to an upstream file must be small, marked, and recorded in
  [DECISIONS.md](DECISIONS.md) so merges can re-apply it consciously.
- Never rewrite large parts of the project without a clear architectural reason and an
  accepted ADR.

## 2. Layering rules

- New platform code lives in its own cohesive modules with single responsibilities
  (compliance guard, risk engine, AI advisor, audit log — separate modules, composed).
- Dependencies point inward: our modules may import freqtrade core; core must not
  import our modules except at explicit, minimal hook points.
- No business logic in RPC handlers — they render; `RPC`/engine decide.
- No trading logic in strategies beyond signal generation and callbacks; hard rules
  (compliance, risk limits) belong in engine-level guards a strategy cannot override.

## 3. Safety invariants (never break)

1. The bot must always be able to *exit* positions — guards may block entries, never
   block exits or stoplosses.
2. Compliance and risk guards fail **closed** (no trade) on error or uncertainty.
3. `strategy_safe_wrapper` semantics stay intact: a crashing callback must not kill
   the loop.
4. Dry-run must remain a faithful path: every new feature works identically in dry-run.
5. Database schema changes must extend `persistence/migrations.py::check_migrate`
   (hand-rolled migration system — no Alembic) and be backward compatible.
6. All engine ↔ AI interaction is one-directional: AI produces recommendations; only
   the engine, after L1–L4 validation (ISLAMIC_POLICY.md), places orders.

## 4. Concurrency rules

- The core loop is effectively single-threaded; respect `_exit_lock` usage in
  `freqtradebot.py`. New background work must communicate via thread-safe structures
  (as FreqAI and `MessageStream` do), never mutate engine state directly.
- No new polling loops when a scheduler hook or the existing throttle serves.

## 5. Configuration rules

- Every new feature is config-gated with a safe default (off, or most conservative).
- New config keys go into `config_schema/config_schema.py` with schema validation and
  documentation; secrets only via environment variables.
- Magic numbers live in named constants or config, never inline.

## 6. Observability rules

- Every decision (signal, validation pass/fail, rejection, order, cancel, error) is
  logged with **why**, not just what.
- User-facing events additionally flow through `RPCManager` with a typed
  `RPCMessageType` so Telegram/API surface them.
- Compliance rejections and risk-limit triggers are always both logged and notified.

## 7. Testing rules (summary — see TESTING_STRATEGY.md)

- No phase merges without tests. Guard modules require near-total branch coverage,
  including failure-mode (fail-closed) tests.
- Follow the existing test layout: tests mirror source tree, reuse `conftest.py`
  fixtures, run under pytest-xdist.
