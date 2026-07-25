# Architecture — How This Repository Works

> Verified against the code of Freqtrade `2026.7-dev` (this repo). File:line references
> point at the actual implementation. When upstream is merged, re-verify line numbers.

## 1. High-level shape

Freqtrade is a single-process, single-threaded-core trading bot (background threads exist
for websockets, FreqAI retraining, and the API server). The core loop is time-throttled,
candle-aligned, and event-free — every iteration re-derives state from the exchange, the
database, and strategy dataframes.

```
CLI (freqtrade trade)
  └─ main.py → Arguments → subcommand dispatch          freqtrade/main.py:31
      └─ Worker (throttled loop, state machine)          freqtrade/worker.py:31
          └─ FreqtradeBot (the trading engine)           freqtrade/freqtradebot.py:79
              ├─ Exchange (ccxt wrapper)                 freqtrade/exchange/exchange.py:121
              ├─ IStrategy (user logic, resolver-loaded) freqtrade/strategy/interface.py
              ├─ PairListManager / ProtectionManager     freqtrade/plugins/
              ├─ Wallets                                 freqtrade/wallets.py
              ├─ DataProvider                            freqtrade/data/dataprovider.py:39
              ├─ Persistence (SQLAlchemy)                freqtrade/persistence/
              └─ RPCManager → Telegram/API/Webhook/Discord  freqtrade/rpc/
```

## 2. Startup flow

1. `main()` sets up logging, parses args, dispatches subcommand (`main.py:31-52`).
2. `trade` → `start_trading()` → `Worker(args).run()` (`commands/trade_commands.py:9`).
3. `Worker._init()` loads config via `Configuration.get_config()` and constructs
   `FreqtradeBot` (`worker.py:52-55`).
4. `FreqtradeBot.__init__` (`freqtradebot.py:79`) in order: exchange → strategy →
   `validate_config_consistency` → `init_db` → `Wallets` → trading/margin mode →
   `RPCManager` → `DataProvider` → `PairListManager` → optional
   `ExternalMessageConsumer` → initial pairlist refresh → initial state →
   (FUTURES-only funding scheduler) → `strategy.ft_bot_start()` → `ProtectionManager`.
5. `Worker.run()` loops forever; `_throttle()` sleeps to the next candle boundary
   (`worker.py:145-177`). `RELOAD_CONFIG` state rebuilds everything (`worker.py:214`).

## 3. The trading iteration — `FreqtradeBot.process()` (`freqtradebot.py:257`)

In order: reload markets → fix missing fees → load open trades → refresh whitelist
(pairlists + open-trade pairs) → refresh candles → `bot_loop_start` → `strategy.analyze`
→ `manage_open_orders` → `exit_positions` → position adjustment (DCA) → if RUNNING and
free slots: `enter_positions` → scheduler/commit/RPC flush.

### Entry path and validation order
`enter_positions` (`:613`) checks the **global pair lock** (`PairLocks.is_global_lock`,
`:638`) then per pair: `create_trade` (`:671`) → free slot check → `get_entry_signal` →
**per-pair lock check** → stake from `Wallets` → optional order-book depth check →
`execute_entry` (`:882`) → price/stake/leverage via `get_valid_enter_price_and_stake` →
**`confirm_trade_entry` strategy veto** (`:932`) → `exchange.create_order` (`:950`).

### Exit path
`exit_positions` → `handle_trade` (`:1355`) → `get_exit_signal` →
`strategy.should_exit()` (ROI / stoploss / trailing / exit signal / custom_exit as
`ExitCheckTuple` list) → **`confirm_trade_exit` veto** (`:2147`) → order.

### Protections (native circuit breakers)
After stoploss/exit fills, `handle_protections` (`:2449`) runs `stop_per_pair` and
`global_stop`. Handlers (`freqtrade/plugins/protections/`): **MaxDrawdown** (global),
**StoplossGuard** (global+pair), **CooldownPeriod** (pair), **LowProfitPairs** (pair).
Triggering writes `PairLock` rows ("*" = all pairs) which gate the entry path above.

## 4. Where leverage / short / futures are decided (Sharia-critical)

- `trading_mode` config enum `spot|margin|futures` (`constants.py:112`,
  `config_schema/config_schema.py:201`), runtime `TradingMode` StrEnum.
- **Shorts**: `get_entry_signal` emits SHORT only if `trading_mode != SPOT` **and**
  `strategy.can_short` (default `False`) (`strategy/interface.py:1376-1382`).
- **Leverage**: `get_valid_enter_price_and_stake` (`freqtradebot.py:1153-1171`) — in SPOT
  the leverage is hard-forced to `1.0`; only non-SPOT consults the `strategy.leverage()`
  callback and exchange max-leverage.
- **Exchange layer**: `Exchange.__init__` resolves the mode (`exchange.py:208-217`);
  `validate_trading_mode_and_margin_mode` (`:927`) returns early for SPOT;
  `_lev_prep` (`:1408`) is a no-op for SPOT and the *sole* gateway to
  `set_margin_mode`/`_set_leverage`; `get_funding_fees` returns 0.0 unless FUTURES
  (`:3981`); `get_liquidation_price` returns None for SPOT (`:4007`).
- Interest calculations exist only in `freqtrade/leverage/interest.py` (margin trading).

**Conclusion:** upstream SPOT mode is already structurally riba-free at runtime, and
since Phase 1 this is *irreversible* for a trading process: `freqtrade/islamic/`
(`enforce_spot_only` in `Worker._init`; `assert_spot_operation` in `_set_leverage` /
`set_margin_mode`) aborts non-spot configs at startup and blocks leverage/margin
operations on an armed bot. See ISLAMIC_POLICY.md enforcement table.

## 5. Exchange layer

- Base `Exchange` (`exchange.py:121`, ~4200 lines) wraps three ccxt objects: sync `_api`,
  async `_api_async` (ccxt.pro), and `_ws_async` for OHLCV watching only — order
  placement is always REST. Per-exchange subclasses (Binance, Bybit, OKX, Kraken, Gate,
  Bitget, Hyperliquid, …) override capability dicts (`_ft_has`) and specialized methods.
- Dry-run branches inside each mutating method; simulated orders in
  `_dry_run_open_orders` (`exchange.py:252`, `create_dry_run_order` `:1143`).
- Stoploss-on-exchange support is per-exchange via `_ft_has["stoploss_on_exchange"]`
  (`create_stoploss` `:1558`).
- Error → freqtrade exception mapping with `@retrier` throughout.

## 6. Strategy system

- `IStrategy` (`strategy/interface.py`): populate callbacks
  (`populate_indicators/entry_trend/exit_trend`), lifecycle callbacks
  (`confirm_trade_entry/exit`, `custom_stoploss`, `custom_exit`, `custom_stake_amount`,
  `adjust_trade_position`, `leverage`, `bot_loop_start`, `informative_pairs`).
  All invoked through `strategy_safe_wrapper` (exceptions can't kill the loop).
- Loaded by `StrategyResolver` (`resolvers/strategy_resolver.py:26`) — part of the
  generic `IResolver` mechanism (`resolvers/iresolver.py:38`) that importlib-loads user
  classes from `user_data/`. Same mechanism serves pairlists, protections, hyperopt
  losses, FreqAI models, and exchange subclasses. **This is the primary extension
  mechanism for the platform — prefer it over editing core.**

## 7. Data

- `DataProvider` (`data/dataprovider.py:39`) is the strategy's data facade: candles,
  analyzed dataframes, orderbook, ticker, external producer dataframes.
- History download + storage in `data/history/`; pluggable `IDataHandler` formats
  (feather default, parquet, json).

## 8. Persistence

- SQLAlchemy 2.x typed models (`persistence/`): `Trade`/`Order` (`trade_model.py`,
  `LocalTrade` holds business logic and also serves backtesting without DB),
  `PairLock`, `KeyValueStore`, `_CustomData` (per-trade custom data), `WalletHistory`.
- `init_db` (`models.py:48`): scoped sessions keyed by request-or-thread id so FastAPI
  and bot threads coexist. SQLite (WAL, StaticPool for in-memory) and PostgreSQL.
- **Migrations are hand-rolled** (`migrations.py` — sentinel-column checks, table rename
  to `*_bak`, copy). No Alembic. Any schema change must extend `check_migrate`.

## 9. RPC / notifications

- `RPCManager` (`rpc/rpc_manager.py:17`) fans `RPCSendMsg` (typed dicts tagged with
  `RPCMessageType`, `enums/rpcmessagetype.py`) out to registered handlers.
- `RPC` (`rpc/rpc.py:112`) is the shared backend for all channels.
- **Telegram** (`rpc/telegram.py`, ~2300 lines): ~40 commands, `@authorized_only`
  chat-id allowlist, inline keyboards for force-enter/exit.
- **API server** (`rpc/api_server/`): FastAPI under `/api/v1`, HTTP-Basic→JWT auth,
  websocket message stream (`/message/ws`) decoupled via an asyncio `MessageStream`.
- Webhook and Discord handlers; `ft_client/` is a standalone pip package REST client.
- Adding a channel = subclass `RPCHandler`, register in `RPCManager.__init__`.
  Adding a message type = extend `RPCMessageType` + `rpc_types.py` + per-channel
  rendering. (This is how AI-recommendation notifications will be added.)

## 10. FreqAI (the existing AI layer)

- `IFreqaiModel` (`freqai/freqai_interface.py:36`) orchestrates train/predict per pair;
  `FreqaiDataKitchen` does feature engineering; `FreqaiDataDrawer` persists models,
  pair dict, and historic predictions. Background thread rescans pairs for retraining
  (`start_scanning` `:213`; window = `train_period_days` + `live_retrain_hours`).
- Models: LightGBM/XGBoost/sklearn/PyTorch (MLP, Transformer) + Reinforcement Learning
  (`freqai/RL/`, gym-style 3/4/5-action envs).
- Strategy integration: `feature_engineering_*`, `set_freqai_targets`,
  `self.freqai.start(...)` in `populate_indicators`.
- **Important:** FreqAI already follows the "AI recommends, engine validates" shape —
  predictions only become entries through normal strategy signals, which still pass all
  engine validations. The RL module's short-selling action spaces must never be enabled
  (see ISLAMIC_POLICY.md).

## 11. Optimization & analysis

- Backtesting engine (`optimize/backtesting.py`; `backtest_loop` `:1521`) converts
  dataframes to fast tuple lists; caching in `backtest_caching.py`.
- **Hyperopt uses Optuna 4.x** (TPE, GP, CMA-ES, NSGA-II/III samplers;
  `optimize/hyperopt/hyperopt_optimizer.py`). The old Edge module has been removed.
- Bias tooling: lookahead-bias and recursive-formula analysis
  (`optimize/analysis/`) — must be part of our strategy acceptance gate.

## 12. Ops

- Docker: root `Dockerfile` + variants (`docker/Dockerfile.freqai`, `.freqai_rl`,
  `.plot`, `.jupyter`, `.armhf`) and compose overrides.
- CI: `.github/workflows/ci.yml` (tests + lint), docker build, docs deploy, dependabot.
- Tests: ~100 files mirroring the source tree; pytest with xdist/asyncio/cov/timeout
  (config in `pyproject.toml [tool.pytest]`); rich fixtures in `tests/conftest*.py`.
- Requirements split: core / dev / hyperopt / freqai / freqai-rl / plot; extras in
  `pyproject.toml` (`freqtrade[all]`).

## 13. Extension points summary (use these; do not fork core logic)

| Need | Mechanism |
|---|---|
| Entry/exit veto (risk, Islamic checks) | `confirm_trade_entry` / `confirm_trade_exit` — **implemented:** L4 order gate in `execute_entry` (Phase 3) |
| Position sizing | `custom_stake_amount`, `Wallets` |
| Circuit breakers / cooldowns | `IProtection` subclass in `user_data/` via resolver |
| Pair universe filtering (compliance screening) | `IPairList` handler/filter — **implemented:** `IslamicComplianceFilter` (Phase 2) |
| New notification (AI decisions, compliance rejections) | `RPCMessageType` + handler rendering |
| New RPC channel | `RPCHandler` subclass registered in `RPCManager` |
| AI models | `IFreqaiModel` subclass via `freqaimodel_resolver` |
| Custom exchange behavior | `Exchange` subclass via `exchange_resolver` |
| Per-trade metadata (audit trail) | `CustomDataWrapper` / `KeyValueStore` |
