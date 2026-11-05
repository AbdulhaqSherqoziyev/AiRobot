# Quant Lab backend

Personal research, paper and controlled live trading for Binance Spot. Long only: no leverage,
shorting or futures exist anywhere in this package. Status and limits:
`.ai/phases/phase-quantlab-platform.md`. Deployment: `deploy/DEPLOY.md`.

```sh
/usr/bin/python3.13 -m venv .venv
.venv/bin/pip install -r quantlab/requirements.txt pytest
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu  # only for LSTM

export QL_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
export QL_OWNER_PASSWORD='choose-a-long-password' QL_SECURE_COOKIES=false
.venv/bin/python -m quantlab.cli migrate
.venv/bin/python -m quantlab.cli download --days 365

.venv/bin/uvicorn --factory quantlab.api.app:app_factory --port 8100 &
for r in market paper jobs notify; do .venv/bin/python -m quantlab.worker $r & done
(cd web && npm install && npm run build && QL_API_URL=http://127.0.0.1:8100 npm start)
# http://127.0.0.1:3100  user: owner

.venv/bin/python -m pytest tests_quantlab -c /dev/null --rootdir=. -p no:asyncio
```

External integrations, optional installs and API: `.ai/integrations/INTEGRATION_REPORT.md`.

| Module | Purpose |
| --- | --- |
| `market/` | Binance public client, Parquet candles, universe scan, WebSocket prices |
| `strategies/` | Standard interface, 10 technical strategies, rule builder |
| `backtest/` | `core.py` is the one simulation used by backtest and paper |
| `paper/` | Persistent virtual sessions; cannot reach any order API |
| `ml/` | Features, walk-forward training, 5 model types, version registry |
| `optimize/` | Optuna search with an out-of-sample check |
| `risk/` | Limits shared by paper and live |
| `evaluation/` | 30-day report and the owner authorization record |
| `live/` | Isolated real-order engine, encrypted keys, kill switch |
| `worker.py` | One process per role: market, paper, jobs, notify, live |
| `api/` | FastAPI control plane |
