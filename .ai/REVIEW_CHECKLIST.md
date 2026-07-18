# Review Checklist

> Run for every phase / PR before it is called done. A failed item blocks merge.

## Compliance (blockers — no exceptions)
- [ ] No code path can set leverage ≠ 1.0, open a short, or call margin/futures
      endpoints (including "dead" code and tests that would normalize it)
- [ ] No interest/funding-rate computation added or made reachable
- [ ] Pair screening not weakened; blacklist/allowlist semantics intact
- [ ] Guards fail **closed**; exceptions inside guards reject the trade
- [ ] Entry-gating only — exits and stoplosses are never blocked
- [ ] Every rejection path logs the reason and (where user-relevant) notifies via RPC

## Correctness
- [ ] Change does exactly what the phase record says — no scope creep
- [ ] Edge cases handled (empty data, exchange errors, restarts, dry-run vs live)
- [ ] Timezone-aware UTC datetimes; exchange precision helpers used for amounts/prices
- [ ] Thread-safety respected (`_exit_lock`, background threads communicate safely)
- [ ] DB schema changes wired through `persistence/migrations.py` and tested

## Architecture
- [ ] Used an extension point (resolver/callback/handler) rather than editing core,
      or the core edit is minimal, marked, and ADR-recorded
- [ ] Single responsibility per module; no duplicated logic (searched for reuse)
- [ ] Config-gated with a safe default; schema + docs updated
- [ ] No new polling loops; no unnecessary network/DB chatter

## Quality
- [ ] Ruff + mypy clean; type hints on all new code
- [ ] Docstrings on public functions; comments explain constraints, not mechanics
- [ ] No magic numbers, dead code, commented-out code, or unreferenced TODOs
- [ ] No secrets in code, logs, or fixtures

## Tests
- [ ] New behavior covered, deny/failure paths included
- [ ] Regression: full `pytest -n auto` green; pre-existing failures unchanged
- [ ] Engine-touching change verified in dry-run
- [ ] Backtest-relevant change checked for lookahead bias (optimize/analysis tools)

## Documentation
- [ ] `.ai/ARCHITECTURE.md` reflects reality
- [ ] ROADMAP status updated; phase record completed (Outcome section filled)
- [ ] ADR written for significant decisions
- [ ] User-facing docs/config examples updated if behavior is user-visible
