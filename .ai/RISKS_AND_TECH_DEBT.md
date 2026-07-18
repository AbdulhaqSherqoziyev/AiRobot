# Risks & Technical Debt Register

> Living document. Reviewed at the start of every stage. Severity: H/M/L.

## Inherited from upstream (facts verified in code)

| # | Item | Sev | Notes / mitigation |
|---|---|---|---|
| U1 | Futures/margin/short machinery ships in the codebase (exchange leverage methods, `freqtrade/leverage/`, RL short actions) — haram paths exist and are only config-gated | H | Roadmap Phases 1–3 make them unreachable by construction; review checklist forbids re-enabling |
| U2 | Hand-rolled DB migrations (`persistence/migrations.py`, table-rename-and-copy; no Alembic) | M | Any schema change must extend `check_migrate`; always test upgrade from a real old DB file; keep backups (Phase 10) |
| U3 | Very large core modules (`exchange.py` ~4200 lines, `telegram.py` ~2300, `rpc.py` ~1800, `freqtradebot.py`) | M | Do NOT refactor upstream files for aesthetics (merge-ability > purity); isolate our code in small modules |
| U4 | Tracking a moving dev branch (`2026.7-dev`) | M | Phase 13 defines sync cadence; pin baseline commit in phase-0 record |
| U5 | Exchange API drift (ccxt updates, exchange quirks) | M | Rely on upstream updates — another reason to stay merge-able |
| U6 | Dry-run fill simulation is optimistic (limit-order fills, no real slippage/partial-fill dynamics) | M | Treat dry-run results as upper bound; pilot phase with tiny capital |
| U7 | Hyperopt/backtest overfitting risk; lookahead bias in user strategies | H | Lookahead & recursive analysis tools are a mandatory acceptance gate (Phase 8) |
| U8 | API server security depends on operator config (JWT secret, ws_token, CORS) | M | Phase 11 security pass + hardened sample config |
| U9 | FreqAI historic predictions persisted via cloudpickle (`data_drawer.py:181`) — unpickling untrusted files is code execution | L | Never load model dirs/predictions from untrusted sources; note in ops runbook |
| U10 | Single-process design; no HA story | L | Acceptable for this platform's scale; document restart behavior instead |

## Our project risks

| # | Item | Sev | Notes / mitigation |
|---|---|---|---|
| P1 | Compliance guard bugs could either block all trading (annoying) or silently allow haram trades (unacceptable) | H | Fail-closed design; near-total branch coverage; audit log makes silent failure visible |
| P2 | Divergence from upstream at our hook points (config_validation, execute_entry, exchange init) | M | Keep hooks tiny + marked; ADR per hook; Phase 13 merge playbook |
| P3 | AI overconfidence → over-trading | H | Confidence thresholds + risk engine caps + protections; constitution: fewer, safer trades |
| P4 | Documentation drift (`.ai/` vs code) | M | Docs-first rule; review checklist item; line references re-verified after upstream merges |
| P5 | Leveraged-token screening false negatives (new naming schemes) | M | Pattern list is config-updatable; audit-mode logging; periodic review |
| P6 | Owner runs live before guards complete | H | ROADMAP sequencing rule: live pilot last, sign-off required |

## Known non-issues (checked, no action)
- Edge module: already removed upstream — nothing to strip.
- Shorting in SPOT: structurally blocked upstream (`interface.py:1376-1382`); we add
  belt-and-suspenders anyway.
- scikit-optimize abandonware risk: gone — hyperopt now uses Optuna.

## Debt log (ours — currently empty)
| Date | Item | Why accepted | Payback plan |
|---|---|---|---|
