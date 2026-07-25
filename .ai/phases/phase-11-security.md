# Phase 11 — Security pass

Status: done (config-validation part); manual checklist ongoing
Started: 2026-07-26   Finished: 2026-07-26

## Goal
Enforce minimum security hygiene at startup and document the operational security
checklist for deployment / live.

## Reason
Constitution "Security": never expose secrets; least-privilege keys; validate
inputs. Required before any live run.

## Design
- `freqtrade/islamic/security.py::validate_security_config()` (hooked in
  `Worker._init` after risk validation, trading path only):
  - live mode (`dry_run=False`) requires non-empty exchange key + secret;
  - an API server bound to a non-loopback address requires a strong
    `jwt_secret_key` (≥16), a username, and a non-weak password — else abort.
  Deterministic, exchange-agnostic, fails closed.
- `.ai/SECURITY_CHECKLIST.md`: operational items that cannot be auto-verified
  (exchange key withdrawal-disabled + spot-only + IP allowlist, secrets rotation,
  host hardening, backups).

## Files affected
- new: `freqtrade/islamic/security.py`, `tests/islamic/test_security.py`,
  `.ai/SECURITY_CHECKLIST.md`
- edited: `freqtrade/islamic/__init__.py`, `freqtrade/worker.py` (hook)

## Expected result
Starting live without credentials, or with an insecurely-exposed API server, aborts
with a clear message. Manual checklist gates the live deployment.

## Risk
Blocking a legitimate startup. Mitigated: dry-run and local-API configs untouched
(default_conf + worker/main suites 26 passed); only genuinely unsafe configs abort.

## Testing — DONE
- 8 tests: dry-run needs no creds; live requires creds; local API no hardening;
  exposed API requires strong jwt / username+password; hardened OK; Worker aborts
  on exposed insecure API.
- Regression: worker/main 26 passed; full suite clean vs baseline.

## Outcome
Delivered the deterministic, testable security config validation + a documented
manual checklist. Exchange-side key-permission verification (no-withdrawal) is
exchange-specific and left to the checklist (verified in the exchange UI) rather
than a fragile live API probe at startup.
