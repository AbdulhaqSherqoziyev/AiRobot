# Deploying Quant Lab to a VPS

**Status: these files were validated with `docker compose config` only. They have not been
built or run: Docker was unavailable on the development machine. Expect to fix small issues on the
first real deploy, and do the checklist at the end before trusting the system.**

## Requirements

Ubuntu 22.04+, Docker with the compose plugin, a domain pointing at the server.
Measured locally: API plus four workers idle at about 1 GB RAM together (not a load test).
Suggested minimum 2 vCPU, 4 GB RAM, 40 GB disk. ML training uses more: LSTM needs PyTorch, which
is not in the image by default (add it to `quantlab/requirements.txt` to enable that algorithm).

## First deploy

```sh
git clone <repo> /opt/airobot && cd /opt/airobot/deploy
cp .env.example .env && chmod 600 .env && nano .env

# TLS certificate, before nginx starts
sudo certbot certonly --standalone -d "$DOMAIN"

docker compose up -d --build
docker compose logs -f migrate api
docker compose exec api python -m quantlab.cli download --days 500 --timeframe 1h
```

Remove `QL_OWNER_PASSWORD` from `.env` after the first start.

Firewall: allow only 22, 80, 443. Postgres and the API have no published ports.

## Backups

`deploy/backup.sh` from cron. Restore:

```sh
docker compose exec -T postgres pg_restore -U quantlab -d quantlab --clean < db-XXXX.dump
```

Test a restore before relying on it.

## Starting the 30-day evaluation

Evaluation Center, then "30 kunlik sinovni boshlash". Criteria freeze at that moment.

## Live trading: the order of gates

All of these must be true, and none happens automatically:

1. The run has finished and a final report exists.
2. The chosen strategy passed the report's criteria.
3. You authorized it in the app: exact confirmation text and your password.
4. Binance API key stored in Settings: spot only, no withdrawal, IP restricted, on a dedicated
   sub-account holding only the allocated funds. The engine checks the key's rights and refuses.
5. `QL_LIVE_ENABLED=true` in `.env`, and the worker started:
   `docker compose --profile live up -d`.
6. You press Start in the Live center, with your password.

Before real money, run the whole flow on Testnet with Testnet keys.

## Checklist after deploy

- [ ] `https://$DOMAIN/` shows the login; HTTP redirects to HTTPS
- [ ] Monitoring page: all workers green, WebSocket connected, datasets syncing
- [ ] External port scan shows only 22, 80, 443
- [ ] `docker compose restart worker-paper`: sessions continue, no duplicate trades
- [ ] Reboot the VPS: everything returns; paper sessions continue
- [ ] Backup runs and a restore works
- [ ] Testnet drill: start, order, kill switch, restart

## Without a domain: SSH tunnel

Publishes nothing to the internet and uses `QL_WEB_PORT` (default 3200). Check first that
the port is free on the server, and that the stack fits beside whatever already runs there.

```sh
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml up -d --build
docker compose exec api python -m quantlab.cli download --days 500 --timeframe 4h
docker compose exec api python -m quantlab.cli paper-watch
```

`paper-watch` starts ATR Volatility 4h with volatility sizing, as one virtual 100 USDT session per
pair. It places no orders. The candidate did not pass the November 2026 study, so this is
observation on new data, not a recommendation to trade it.

## This server: icash.uz

Running at `/opt/quantlab`, compose project `quantlab`, beside other projects. Do not `rsync --delete`
into it: that would remove `deploy/.env`, which holds the secret key. Copy changed files instead.

- `admin.icash.uz`: the control centre
- `icash.uz`: serves nothing, on purpose; connections are closed
- `api.icash.uz`: the API
- `app.icash.uz`: another project, not part of this stack

HTTPS is on since 2026-11-04, by `deploy/enable-domain.sh`. `COMPOSE_FILE` in `deploy/.env` selects the
tunnel and domain overrides, so plain `docker compose` commands keep the right ports.
