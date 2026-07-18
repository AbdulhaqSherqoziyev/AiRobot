# Coding Standards

> Applies to all new and modified code. Match the surrounding upstream style when
> editing upstream files.

## 1. Language & tooling (as configured in this repo)

- Python ≥ 3.11 (see `pyproject.toml`). Use modern typing (`Mapped[]`, `X | None`,
  `StrEnum`) as upstream does.
- Formatting/linting: **ruff** (config in `pyproject.toml`); run before commit.
- Types: full type hints on all new code; keep mypy clean for our modules.
- Tests: pytest (+ asyncio auto mode, xdist); tests mirror the source tree under
  `tests/`.
- Pre-commit hooks as configured in `.pre-commit-config.yaml`.

## 2. Design

- SOLID, DRY, KISS; high cohesion, low coupling; composition over inheritance except
  where upstream idiom is subclassing (exchanges, pairlists, protections, models).
- Small modules and small functions; one responsibility each.
- Domain language: name things after trading/compliance concepts
  (`ComplianceGuard`, `RiskLimit`, `TradeRecommendation`), not implementation details.
- Reuse upstream primitives: resolvers for pluggability, `RPCMessageType` for events,
  `KeyValueStore`/`CustomDataWrapper` for persistence, protections for locks. Do not
  reinvent them.

## 3. Code rules

- No magic numbers — named constants (`freqtrade/constants.py` pattern) or config.
- Every public function/class: docstring stating purpose, params, return, and — for
  guards — failure behavior.
- Complex logic gets a comment explaining the constraint, not the mechanics.
- No commented-out code, no dead code, no "temporary" hacks, no TODO without a
  roadmap/issue reference.
- Exceptions: use the existing hierarchy (`freqtrade/exceptions.py`); never swallow
  exceptions silently; guards fail closed on exception.
- Logging: module-level `logger = logging.getLogger(__name__)`; messages state the
  decision **and its reason**; never log secrets.
- Datetime: timezone-aware UTC (upstream `dt_now()` helpers in `freqtrade/util`).
- Money/quantities: follow upstream conventions (floats with exchange
  precision helpers — `amount_to_precision`, `price_to_precision`); never round
  manually.

## 4. Error handling & I/O

- All exchange calls go through the `Exchange` wrapper (retries, exception mapping) —
  never call ccxt directly from feature code.
- Network/API interactions must be resilient: retry-able errors use existing retrier
  patterns; hard errors surface as typed exceptions.
- Validate all external inputs (config via JSON schema; API via Pydantic models).

## 5. Tests

- New behavior ⇒ new tests; bug fix ⇒ regression test first.
- Use existing fixtures (`tests/conftest.py`, `conftest_trades.py`) and mocking
  patterns; no live-exchange calls in unit tests.
- Guard/compliance modules: test the *deny* paths as thoroughly as the allow paths,
  including exception-in-guard ⇒ trade rejected.

## 6. Commits & PRs

- Small commits, one logical change, imperative subject line.
- PR description links the phase record in `.ai/phases/` and states test evidence.
