# Quant Lab platform — status record

Date: 2026-11-04. Spec: the owner's "Autonomous Quant Trading System". Decisions: ADR-0007 to 0009.
Audit: [AUDIT_QUANT_PLATFORM.md](../AUDIT_QUANT_PLATFORM.md).

## Verification levels used below

- **Real:** exercised with real Binance public data on the development machine.
- **Tests:** covered by automated tests with fakes.
- **Not run:** written, but never executed.

| Area | Level | Notes |
| --- | --- | --- |
| Market data, Parquet store, gaps, duplicates, universe scan | Real + tests | 9 pairs, 12k 1h candles |
| WebSocket price stream | Real + tests | data-stream.binance.vision; reconnect tested with a fake |
| 10 technical strategies, look-ahead test | Real + tests | All lost money on real data, see Results |
| Rule builder strategies | Real + tests | |
| Backtest engine and metrics | Real + tests | |
| Paper engine, restart, isolation | Real + tests | See restart test below |
| LightGBM, XGBoost, Random Forest, LSTM, RL | Real + tests | No predictive edge found, see Results |
| Optuna optimizer with OOS | Real + tests | |
| Evaluation report and approval | Tests | A real 30-day run has not happened |
| Risk rules | Tests | |
| Live engine, kill switch | Tests | Fake exchange only |
| Signed Binance client, Testnet | Not run | No Testnet keys were used |
| Telegram delivery | Tests | Never sent a real message |
| Docker images, compose | Real | Running on the VPS at `/opt/quantlab`, reached by SSH tunnel |
| PostgreSQL | Real | Migrations, sessions, backtest, backup and restore on the VPS |
| Host Nginx, TLS, public domains | Not run | Waiting for `.uz` delegation; `deploy/enable-domain.sh` is ready |
| Full VPS reboot | Not run | Shared server; container restarts were tested instead |
| Web app | Real | 18 screens in a browser against the real API, at 390 px and in loading, empty and error states |

## Results on real data (BTC/USDT 1h, about 400-500 days, fee 0.1%, slippage 0.05%)

Every technical strategy with default parameters lost between 18% and 57%, worse than or close to
buy and hold over the same window. ML out-of-sample AUC was 0.50-0.54, which is close to chance.
This is the current honest state. No strategy is near the live criteria.

Follow-up study with a pre-registered holdout: [research/2026-11-strategy-optimization.md](../research/2026-11-strategy-optimization.md). No candidate was confirmed.

## Known gaps

- Partial fills are not modelled. Order book and raw trades have client methods but are not stored.
- Strategy version parameter editing covers numeric parameters; ML optimizer is not implemented.
- Redis from the spec is not used: the job queue is a database table (simpler, survives restarts).
- Tailwind and shadcn/ui from the spec are not used: screens keep the design's inline styles.
  Generated and live screen files carry `@ts-nocheck`.
- Generated screens still contain some static explanatory text from the design.
- Only one open position per session and one pair per live authorization.
- ML features ignore order book data.
