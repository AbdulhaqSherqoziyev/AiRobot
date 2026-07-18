# Testing Strategy

## Inherited infrastructure (use it, don't reinvent)

- pytest configured in `pyproject.toml` (`asyncio_mode=auto`, xdist `loadscope`,
  timeout, random-order, coverage plugins in `requirements-dev.txt`).
- ~100 test files under `tests/` mirroring the source tree; rich fixtures in
  `tests/conftest.py`, `conftest_trades.py`, `conftest_trades_usdt.py`,
  `conftest_hyperopt.py`; static market data in `tests/testdata/`.
- CI: `.github/workflows/ci.yml` (tests + lint across platforms).
- Standard run: `pytest -n auto`; lint: `ruff check . && ruff format --check .`.

## Test pyramid for our work

1. **Unit** (bulk): guard logic, filters, protections, sizing — pure functions where
   possible, fixture-mocked exchange otherwise. Deny/failure paths get equal weight
   with allow paths.
2. **Integration**: through real engine seams — `PairListManager.refresh_pairlist`,
   `execute_entry` with mocked exchange, protections via `ProtectionManager`,
   RPC rendering per channel. Follow existing upstream test idioms in
   `tests/freqtradebot/`, `tests/plugins/`, `tests/rpc/`.
3. **Backtest determinism**: reference strategy backtests pinned to fixed data with
   asserted results; lookahead (`optimize/analysis/lookahead.py`) and recursive
   analysis must be clean for any strategy we ship.
4. **Dry-run smoke** (manual, evidence recorded in phase record): bot starts, trades
   simulate, guards observably reject a crafted non-compliant scenario.
5. **Live pilot** (Phase 14 only): tiny capital, predefined exit criteria.

## Compliance-specific requirements

- A dedicated test module per enforcement layer (L1 config … L6 audit) proving:
  - non-spot configs abort startup;
  - leverage/margin calls raise;
  - haram pairs never reach the whitelist (incl. tricky ticker names);
  - entry gate blocks each forbidden condition and *logs the reason*;
  - guard-internal exception ⇒ trade rejected (fail-closed);
  - exit paths run even while every entry guard is tripped.
- These tests are regression-frozen: they may be extended, never weakened, and any
  edit to them is a compliance-review event.

## Migration testing

Schema changes: keep a copy of a pre-change SQLite file in `tests/testdata/` style and
assert `check_migrate` upgrades it losslessly.

## Rules

- No live exchange calls in tests (upstream `exchange_online/` tests are opt-in; we
  don't add to them without reason).
- New bug ⇒ regression test written before the fix.
- CI must be green before a phase is declared done; flaky tests are fixed or
  quarantined with a tracked issue, never ignored.
