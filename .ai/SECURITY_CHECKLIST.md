# Security Checklist

Operational security for the platform. Automated checks are enforced at startup by
`freqtrade/islamic/security.py` (`validate_security_config`); the manual items below
must be verified before any live run and re-checked on each deployment.

## Exchange API keys (least privilege) — before live
- [ ] **Withdrawals DISABLED** on the API key. (Exchange-side; cannot be reliably
      verified via ccxt for all exchanges — verify in the exchange UI.)
- [ ] **Spot trading enabled only** — margin/futures NOT enabled on the account/key.
- [ ] **IP allowlist** set to the exact server IP running the bot. Note: the server
      IP (`157.173.123.206`) must be whitelisted, not the dev machine.
- [ ] Keys supplied via **environment variables** (`FREQTRADE__EXCHANGE__KEY` /
      `FREQTRADE__EXCHANGE__SECRET`), never committed. `.env*` is gitignored.

## Secrets hygiene
- [ ] No secrets in `config*.json`, code, logs, or the repo. Grep before commit.
- [ ] Rotate any secret ever pasted into a chat/ticket (Telegram bot token, PATs,
      exchange keys, server passwords).
- [ ] Server root password rotated after setup; prefer SSH-key-only login.

## API server exposure (enforced at startup for non-local binds)
- [ ] Prefer binding to `127.0.0.1`; expose only behind a reverse proxy + TLS.
- [ ] If bound to a public IP: strong `jwt_secret_key` (≥ 16 chars, random),
      non-default `username`, strong `password`, restricted `CORS_origins`.
- [ ] `ws_token` (websocket) set to a strong random value if the WS feed is used.

## Host / deployment
- [ ] Bot runs as a non-root user where possible; least-privilege file permissions
      on `.env` (`chmod 600`).
- [ ] Firewall: only required ports open; API port not world-exposed.
- [ ] DB and FreqAI model files backed up; never load untrusted pickled models
      (cloudpickle = code execution).
- [ ] Dependency audit (`pip-audit` / GitHub Dependabot) reviewed.

## Compliance interplay
- [ ] Spot-only (L1/L2), pair screening (L5), order gate (L4), risk limits and the
      circuit breaker are all active in the deployed config (see ISLAMIC_POLICY.md).
