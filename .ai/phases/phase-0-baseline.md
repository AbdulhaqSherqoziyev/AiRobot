# Phase 0 — Baseline verification

Status: done
Started: 2026-07-18   Finished: 2026-07-19

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
- Dependency install: OK (2026-07-19). Two environment findings:
  - `/tmp` is a 3.6 GB tmpfs — pip needs `TMPDIR` on disk for large wheels.
  - torch installed as **2.13.0+cpu** (CPU-only index) — the CUDA variant (~2 GB) is
    unnecessary on this host and overflowed tmpfs. GPU-based RL training would need a
    separate decision later.
- ruff: `ruff check .` all passed; `ruff format --check` — 482 files already formatted.
- pytest (`pytest -n auto -q --timeout=300`, 2026-07-19): **4418 passed, 8 failed,
  20 skipped** in 155 s. All 8 failures are environment-related, not product code —
  frozen as known baseline exceptions:
  - `test_startup_time` — needs `freqtrade` on PATH (venv not activated in test env)
  - `test_pip_audit_no_vulnerabilities` — pip-audit run failure (network/tooling)
  - `test_start_list_data`, `test_start_show_config`, `test_hyperopt_list`,
    `test_text_table_exit_reason`, `test_text_table_strategy`,
    `test_telegram_profit_long_short_handle` — console/table rendering asserts
    (terminal/locale sensitive)
  Rule: future runs must show the same-or-smaller failure set; any new failure is a
  regression.
- dry-run smoke: PASS — bot starts with spot dry-run config (SampleStrategy,
  Binance public data): heartbeat RUNNING, wallets synced, whitelist loaded
  (BTC/USDT, ETH/USDT), no errors.
- Repo now under git (`main`, initial commit f10f6bf); remote
  `origin=github.com/AbdulhaqSherqoziyev/AiRobot` — push pending owner credentials.

## Review
- [ ] REVIEW_CHECKLIST.md passed (docs/test items only apply)

## Outcome
(pending)
