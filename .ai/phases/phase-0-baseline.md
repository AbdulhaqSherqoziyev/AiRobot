# Phase 0 — Baseline verification

Status: in-progress
Started: 2026-07-18   Finished: —

## Goal
Reproducible dev environment; upstream lint/test suite executed and its results
recorded as the trusted baseline for all future work.

## Reason
Roadmap Phase 0 — later regressions must be attributable against a known-good state.

## Compliance check (mandatory)
- Touches order placement / leverage / shorting / pair selection / funding? **no**
  (environment + verification only; no code changes)

## Design
- Local `.venv` (Python 3.13.12, Kali Linux, externally-managed system Python).
- Install `requirements-dev.txt` + editable install (`pip install -e .`).
- Record: dependency install result, `ruff check`, full `pytest -n auto` outcome,
  dry-run smoke test.
- Repo state: **not a git repository** (plain source tree of upstream `2026.7-dev`).
  Baseline pinning by version string only; recommend `git init` + import of upstream
  history in a future ops phase.

## Files affected
None in source. `.venv/` created (untracked tooling), this record.

## Expected result
Documented green (or documented-failure) baseline.

## Risk
None to code. Possible flaky/env-dependent upstream tests — will be listed here, not
"fixed".

## Rollback plan
Delete `.venv/`. No source changes.

## Testing requirements
- `ruff check .`
- `pytest -n auto` (full suite)
- `freqtrade trade --dry-run` smoke test with a generated spot config (config kept in
  job tmp dir, not committed)

## Documentation updates
This record; ROADMAP status flip on completion.

## Results (filled as executed)
- Python: 3.13.12 (`.venv`)
- Dependency install: (pending)
- ruff: (pending)
- pytest: (pending)
- dry-run smoke: (pending)

## Review
- [ ] REVIEW_CHECKLIST.md passed (docs/test items only apply)

## Outcome
(pending)
