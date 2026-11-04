# Repository Audit — Personal Quant Platform Extension

> Audit date 2026-11-04, checkout `worktree-mighty-snacking-dahl` @ `5ff8dff`. Read-only,
> except this file. Test suite not run; figures come from `.ai/phases/`.
> **[I]** = inferred, not verified in code or by running it. Everything else was read or
> executed here. Paths are repo-relative. Line numbers shift on upstream merges.

## 0. Verdict

Freqtrade already provides the engine, dry-run, backtest, hyperopt (Optuna), most ML models, Parquet storage, REST API and Telegram. Missing: a **control plane** (sessions, approvals, evaluation, data catalog), the web app, LSTM, a long-only RL env, 14 strategies, and a deployment that actually runs this fork. No core rewrite is needed.

Must fix first: `docker-compose.yml` runs upstream's image, without any Islamic guard (R1); `.venv` is broken (R2); root `.gitignore` is silently dropping `web/src/lib/` and misses `.env.*` (R3).

Correction to the brief: "Phases 0-11" were not all done. Records exist for 0-6, 8 (re-scoped) and 11 only (`.ai/phases/`). Phases 7, 9, 10, 12, 13, 14 are open.

## 1. Current architecture

### Packages in `freqtrade/` (`.py` file count)

| Package | Role |
|---|---|
| `commands/` (17) | CLI subcommands; `trade_commands.py:24` builds `Worker`, `webserver_commands.py:12` builds a standalone API |
| `configuration/`, `config_schema/` (12, 2) | Config load/merge, env overrides, JSON-schema validation |
| `data/` (21) | `dataprovider.py`, `history/` + pluggable datahandlers, `metrics.py`, `btanalysis/` |
| `exchange/` (30) | ccxt wrapper (`exchange.py`, 4162 lines), dry-run order simulation, per-exchange subclasses, `binance_public_data.py` |
| `freqai/` (46) | ML layer: `prediction_models/`, `base_models/`, `RL/`, `torch/`, data kitchen/drawer |
| `islamic/` (6) | **Custom.** Guards (see below) |
| `leverage/` (3) | Margin/liquidation calculations; unreachable in spot (ISLAMIC_POLICY.md:48) |
| `optimize/` (38) | Backtesting, hyperopt, `optimize_reports/`, lookahead/recursive analysis |
| `persistence/` (12) | SQLAlchemy models (Trade, Order, PairLock, KeyValueStore, WalletHistory), hand-rolled migrations |
| `plugins/` (34) | Pairlists and protections (includes custom filter + 2 custom protection files) |
| `resolvers/` (8) | importlib class loading from `user_data/` (strategy, FreqAI model, pairlist, ...) |
| `rpc/` (34) | `rpc.py` shared backend; `telegram.py`, `webhook.py`, `discord.py`; `api_server/` FastAPI |
| `strategy/` (9) | `IStrategy` (`interface.py`), parameters (`hyper.py`, `parameters.py`) |
| `enums/`, `ft_types/`, `mixins/`, `loggers/`, `system/`, `util/`, `vendor/`, `plot/`, `templates/` | Support code and strategy templates |

Outside the package: `ft_client/` is a standalone REST client (`ft_rest_client.py`).

### Custom vs upstream

`f10f6bf` is the baseline import; 19 commits follow. `git diff f10f6bf HEAD` outside `.ai/` is 35 files, +2029/-1, but part of it is upstream files re-added by `f3bdff7` (UI fallback, test configs, docker overlays). Actual custom code:

| Item | Location |
|---|---|
| L1/L2 spot-only | `islamic/compliance.py:59,81` |
| L5 screening | `islamic/screening.py:35,60`, `plugins/pairlist/IslamicComplianceFilter.py:21` |
| L4 order gate | `islamic/order_gate.py:25` |
| Risk / security startup checks | `islamic/risk_config.py:23`, `islamic/security.py:30` |
| Protections | `plugins/protections/max_loss_protection.py:74,84`, `consecutive_loss_guard.py:25` |
| Strategy, config | `user_data/strategies/IslamicSpotStrategy.py`, `config_examples/config_islamic_spot.example.json` |
| Tests | 61 test functions: `tests/islamic/` plus 3 files in `tests/plugins`, `tests/strategy` |

Core hooks are small, as ADR-0001 requires: `worker.py:56-60`, `exchange.py:3773,3826`, `freqtradebot.py:921`, `constants.py:77`.

## 2. Reuse map

| Component | Verdict | Modules / work |
|---|---|---|
| Next.js control centre | BUILD NEW | `web/` (in progress elsewhere). Talks only to the control plane, never to bots |
| REST API | EXTEND | Bot API as is (per session) + new FastAPI control plane using `ft_client` |
| OHLCV/parquet | REUSE | `download-data --data-format-ohlcv parquet`, `parquetdatahandler.py:8` |
| Market-data scheduler, catalog, gap checks | BUILD NEW | Job + Postgres catalog table |
| PostgreSQL | BUILD NEW | Control-plane schema; driver absent (see section 4) |
| 15 strategies, standard interface | EXTEND | `IStrategy` + new `AiRobotBaseStrategy`; 14 new strategies in `user_data/strategies/` |
| ML: LightGBM, XGBoost, RandomForest | REUSE | See FreqAI below |
| ML: LSTM | BUILD NEW | Model on `BasePyTorchRegressor` |
| ML: RL | EXTEND | Long-only env required (policy) |
| Backtesting | REUSE | `optimize/backtesting.py`; wrap in job runner |
| N paper sessions | EXTEND | One bot per session (below) + session supervisor (BUILD) |
| Restart survival | REUSE + config | Needs `initial_state: running` (below) |
| 30-day report | EXTEND | `data/metrics.py` + bot API; report generator is BUILD NEW |
| Owner approval | BUILD NEW | Control plane + engine-side startup check |
| Isolated $100 live | EXTEND | `available_capital` + new validator + dedicated sub-account |
| Risk controls | REUSE | Protections listed below |
| Kill switch | EXTEND | Composed from RPC; persistence missing (below) |
| Optuna | REUSE | Hyperopt is already Optuna (below) |
| Telegram | REUSE, restricted | Live bot and control plane only (below) |
| Docker/Nginx/VPS | BUILD NEW | Own image, compose, TLS. Only upstream's bot-only compose exists |

### Dry-run and N isolated sessions

**One process = one wallet + one strategy + one DB + one API port.** No in-process multi-session is possible without a core rewrite:

- `Trade`/`Order`/`PairLock`/`WalletHistory` share a class-level session set by `init_db` (`persistence/models.py:86-95`); `PairLocks` is class state (`pairlock_middleware.py:21`).
- One `FreqtradeBot` per `Worker`; one starting wallet (`wallets.py:47`); one listen port (`webserver.py:297-298`).

**Recommended: one container per session**, each with:

| Per-session setting | Value |
|---|---|
| Config overlay | `dry_run: true`, `dry_run_wallet: 100`, `initial_state: running`, `bot_name`, Telegram off, `force_entry_enable: false` |
| DB | Own SQLite via `db_url` (schema `config_schema.py:805`) on a session volume |
| API | Own secrets; private Docker network, no published port. Binding `0.0.0.0` makes `security.py:48-60` demand a strong JWT secret and password, which suits generated per-session secrets |
| Files | `user_data` volume: logs, FreqAI models, strategy snapshot (hash recorded) |
| FreqAI | Unique `freqai.identifier` (`freqai_interface.py:69`) |
| Restart | Docker `restart: unless-stopped` |

No exchange keys are needed in paper containers ([I] for all flows; the Phase 0 smoke test ran on public data). Constraints to validate before committing to a session count:

- **Binance IP limits.** Each process has its own ccxt limiter, so there is no shared budget [I]. Mitigate: `StaticPairList` (not `VolumePairList`), staggered starts, WebSocket candles (default on for Binance spot: `exchange.py:287`, `binance.py:47`). Load-test 5 → 15 → 30.
- **RAM/CPU.** [I] roughly 300-500 MB per plain bot, 1-2 GB+ per torch bot; FreqAI retraining runs in each bot and is CPU-bound. Measure on the real VPS. Expect ML sessions to set the ceiling, and consider fewer pairs or longer `live_retrain_hours` for them.

### Persistence on restart (verified)

| State | Survives? | Evidence |
|---|---|---|
| Trades, orders | Yes | DB |
| Dry-run wallet | Yes, recomputed from DB | `wallets.py:105-120` |
| Open dry-run orders | Yes, rebuilt from DB on lookup | `exchange.py:1384-1401` |
| Protection locks | Yes (`PairLock` rows) | `phase-5-circuit-breaker.md` |
| Daily wallet history | Yes; also in dry-run, one record per day at 00:07 | `wallets.py:449-453`, `freqtradebot.py:176` |
| Candles | No, in memory, refetched | `exchange.py:246` |
| FreqAI models | Yes, on disk, if the volume persists | `data_drawer` / `identifier` |
| **Run state (running/paused/stopped)** | **No, reset from config** | `freqtradebot.py:149-150` |

Two consequences:

- `config_islamic_spot.example.json` has no `initial_state`, so **a restarted session comes back STOPPED** (default at `freqtradebot.py:150`). Sessions must set it to `running`.
- With `running`, a manual `/stop` or `/stopentry` **is undone by a restart** (section 5, R5).

Downtime also leaves paper positions unmanaged, so the evaluation must record gaps. Hourly equity needs control-plane snapshots, as wallet history is daily.

### FreqAI model coverage (`freqai/prediction_models/`)

| Requested | Status | Class |
|---|---|---|
| LightGBM | Exists | `LightGBMRegressor`, `LightGBMClassifier`, `*MultiTarget` |
| XGBoost | Exists | `XGBoostRegressor`, `XGBoostClassifier`, `XGBoostRegressorMultiTarget` |
| RandomForest | Exists | `SKLearnRandomForestClassifier.py:17` (classifier only); `XGBoostRFRegressor`, `XGBoostRFClassifier` |
| LSTM | **Missing** | Only `PyTorchMLP*`, `PyTorchTransformerRegressor`. Add model + regressor; `RecurrentPPO` (`BaseReinforcementLearningModel.py:37`) is RL, not a substitute |
| RL | Exists, **not policy-safe** | `ReinforcementLearner.py:106` defaults to `Base5ActionRLEnv`, which has `Short_enter` (`Base5ActionRLEnv.py:16`) |

`Base3ActionRLEnv` is the right base: Neutral/Buy/Sell, with shorting gated by `can_short` (`Base3ActionRLEnv.py:61-67`). All ML strategies emit dataframe signals through the normal entry path, so they fit ADR-0003. Confidence gating still has to be built (policy §3).

### Hyperopt vs Optuna

Not a choice: hyperopt **is** Optuna (`hyperopt_optimizer.py:14,55-61`). Limits: the study is in memory with no storage (`:438`), so no resume; no REST endpoint exists (only `/hyperoptloss`, `api_webserver.py:45`); it optimises strategy parameters, not model hyperparameters (no Optuna import under `freqai/`). Recommendation: run `freqtrade hyperopt` as a job for strategies; use a small direct Optuna script with Postgres storage for ML, as a later option.

### REST API (`rpc/api_server/`, API version 2.49, `api_v1.py:74`)

Trade-mode and webserver-mode routes are mutually exclusive (`webserver.py:226-277`, `deps.py:68-76`). **A trading bot cannot backtest or list strategies.**

| Need | Endpoint | Mode | Location |
|---|---|---|---|
| Trades | `GET /trades` (default limit 500, offset), `/trade/{id}`, `/status` | trade | `api_trading.py:167,179,157` |
| Balance | `GET /balance`, `/historic_balance` | trade | `:46,:108` |
| Profit | `GET /profit`, `/profit_all`, `/daily`, `/weekly`, `/monthly`, `/performance`, `/stats` | trade | `:80,:85,:124,:135,:146,:75,:103` |
| Candles (live) | `GET/POST /pair_candles` | trade | `:344,:349` |
| Candles (history) | `GET/POST /pair_history` | webserver | `api_pair_history.py:18,47` |
| Control | `POST /start`, `/stop`, `/pause`, `/stopentry`, `/reload_config`, `/forceexit`, `/forceenter`; locks | trade | `api_trading.py:322-339,264,235,300-315` |
| Backtest | `POST/GET/DELETE /backtest`, `/backtest/abort`, `/backtest/history*` | webserver | `api_backtest.py:155-406` |
| Strategies | `GET /strategies` | webserver | `api_webserver.py:23` |
| Strategy source/detail | `GET /strategy/{name}` | any | `api_v1.py:158` |
| Bias analysis | `/lookahead_analysis`, `/recursive_analysis` | webserver | `api_analysis.py:202,115` |
| Data | `POST /download_data` | webserver | `api_download_data.py:51` |
| Ops | `/ping` (public), `/health`, `/logs`, `/show_config`, `/sysinfo` | any | `api_v1.py:82,203,110,98,198` |
| Stream | `WS /message/ws` | any | `api_ws.py:116` |

Webserver mode runs one background analysis/backtest at a time (`api_backtest.py:160`), so parallel research should use CLI job containers.

**Auth:** one username/password per process (`api_auth.py:22`), HTTP Basic or JWT (`:108`), HS256 (`:17`), access token 15 min, refresh 30 days (`:92,:94`), routes `/token/login`, `/token/refresh` (`:124,:151`), separate `ws_token` (`:56`). No roles, no read-only mode, nothing multi-tenant [I from reading `api_auth.py`]. Hence the browser must never hold bot credentials.

### Data formats

Supported: `json`, `jsongz`, `feather`, `parquet` (`constants.py:79`). **Parquet yes**, feather is the default (`config_schema.py:851-855`). Set `dataformat_ohlcv: parquet`. `--prepend` extends history (`history_utils.py:182`). The checkout has 4 pairs at 1h in feather (`user_data/data/binance/`, untracked), which need converting or re-downloading.

### Protections

`MaxDrawdown`, `StoplossGuard`, `CooldownPeriod`, `LowProfitPairs` (upstream) and `MaxDailyLoss`, `MaxWeeklyLoss`, `ConsecutiveLossGuard` (custom) all write global `PairLock`s. Enough for the spec's risk controls. Gap: nothing requires them to be configured (R6).

### Telegram

`rpc/telegram.py` is complete, but it long-polls (`:363`), and one token supports only one poller [I: Telegram API behaviour]. **Do not enable it in paper sessions.** Run one notifier in the control plane, fed by bot webhooks (`rpc/webhook.py`, `rpc_manager.py:42`) or `/message/ws`. The live bot may have its own token. The constitution's message list (`claudeSkills.MD`, `# Telegram`) belongs in that notifier.

## 3. Existing strategies and config examples

**Strategies:** only `user_data/strategies/IslamicSpotStrategy.py`: 1h, long-only EMA50/200 + RSI cross + ADX + volume; ROI ladder, -5% stop, trailing. Phase 8 result: -0.72% vs market -40.81%, profit factor 0.65, lookahead clean; recorded as **not ready for live**. It defines tunables as plain constants (`:41-51`), so neither hyperopt nor parameter files can touch them. It sets no `order_types`, so stoploss-on-exchange stays off. Templates: `freqtrade/templates/` (`sample_strategy.py`, `FreqaiExampleStrategy.py`, `FreqaiExampleHybridStrategy.py`).

**Configs** (`config_examples/`, no real config is tracked):

| File | Notes |
|---|---|
| `config_islamic_spot.example.json` | Canonical. Dry-run wallet 1000, stake 50, 3 trades, **5m** timeframe vs strategy's 1h [I: strategy attribute wins], VolumePairList + filter, all protections, `BNB/.*` blacklisted (`:21-23`), no `api_server`, no `initial_state` |
| `config_binance.example.json` | Upstream; `BNB/.*` blacklisted (`:56-57`), API on 127.0.0.1 (`:70`), no compliance filter |
| `config_freqai.example.json` | Upstream; `force_entry_enable: true` (`:87`), identifier `unique-id` (`:57`). Do not copy as is |
| `config_full.example.json`, `config_kraken.example.json` | Upstream reference; not for this platform |

## 4. Dependencies

| Item | Finding |
|---|---|
| Declared | `requires-python >=3.11`, classifiers up to 3.14 (`pyproject.toml:16,22-25`); CI matrix includes 3.14 (`ci.yml:28`); `Dockerfile:1` uses `python:3.14.6-slim-trixie` |
| System | `python3` = 3.14.8, `python3.13` = 3.13.15; no 3.11/3.12 |
| **`.venv` (main checkout; none in this worktree) is broken** | Created on 3.13.12 (`pyvenv.cfg`), but `bin/python3 -> /usr/bin/python3`, which is now 3.14.8. `bin/python` and `bin/python3.13` both run 3.14.8 and `import sqlalchemy` fails, since packages are in `lib/python3.13/` [I: cause is a system Python upgrade]. Standing instructions to run `.venv/bin/python -m pytest` no longer work |
| `.venv` contents | With `/usr/bin/python3.13` + `PYTHONPATH`, talib, lightgbm, xgboost, sklearn, optuna, torch 2.13.0+cpu, SB3 and pyarrow all import. No `bin/freqtrade`, no editable `freqtrade`, no psycopg |
| Python 3.14 wheels | **Unverified.** PyPI was unreachable from this audit. CI + Dockerfile suggest core works [I]; torch/ta-lib/RL stack on 3.14 is unproven locally |
| PostgreSQL driver | In no requirements file or Dockerfile; docs say `pip install "psycopg[binary]"` (`docs/advanced-setup.md:137`) |
| Images | Base image installs `requirements-hyperopt.txt` only; FreqAI needs `docker/Dockerfile.freqai`, whose default base is `freqtradeorg/freqtrade:develop` (`:1-3`, upstream code) |
| Baseline | Phase 0 (2026-07-19, Python 3.13): 4418 passed, 8 environment failures, 20 skipped |

Recommendation: standardise on **Python 3.13**, the only version with a recorded test baseline; recreate `.venv` with `python3.13 -m venv`, and build images on it. Move to 3.14 after the full FreqAI stack passes there. Give the control plane its own dependency set so its pins never collide with the bot's exact pins (`requirements.txt`).

## 5. Technical debt and risks

| # | Sev | Risk | Evidence | Action |
|---|---|---|---|---|
| R1 | **Critical** | Default Docker runs **upstream code, no guards** | `docker-compose.yml:4` (`freqtradeorg/freqtrade:stable`), `docker/docker-compose-freqai.yml:4`, `Dockerfile.custom:1`; mounts only `user_data` | Build and pin own image. Boot-check that `freqtrade.islamic` is present |
| R2 | High | Dev `.venv` broken | Section 4 | Recreate first |
| R3 | High | `.gitignore` gaps (below) | Below | Fix before any new work is committed |
| R4 | High | Control plane or `web/` becoming a path to live funds | No roles in bot API; Docker socket is root-equivalent [I] | Keys only in live container; socket proxy; approval check in engine |
| R5 | High | **Kill switch does not survive restart, and `/stop` alone stops managing positions** | `freqtradebot.py:149-150`; `worker.py:120-123`; `process_stopped` only cancels orders (`freqtradebot.py:314-319`). Roadmap Phase 5 asked for persistence (`ROADMAP.md:95-97`); only the automatic breaker has it | Kill = `/stopentry` + `/forceexit all` (`rpc.py:1106`). Persist a halt flag and check it on start, entries only |
| R6 | High | Guards are optional in config | `IslamicComplianceFilter` referenced only in `constants.py` outside its own module; `validate_risk_config` checks only `max_open_trades` (`risk_config.py:30-38`) | New validator: filter present and not `audit_mode`; required protections; bounded stake |
| R7 | High | No stop while bot is down in live | `stoploss_on_exchange` unset in config and strategy; Binance spot supports it (`binance.py:36`) | Require it for live |
| R8 | High | Evaluation overstates skill | Dry-run fills optimistic (U6); 15+ strategies in 30 days = multiple comparisons, few trades [I]; Phase 8 not profitable | Pre-commit pass criteria, min trades, fee/slippage haircut, benchmark vs buy-and-hold, single regime warning. Passing is not proof of an edge |
| R9 | Med | Live "isolation" is not automatic | `_update_live` reads the account (`wallets.py:185`); `available_capital` caps only the bot's sizing (`:282-283,300-301`) | Dedicated sub-account with only $100, no-withdraw, IP-locked key |
| R10 | Med | Security checks narrower than documented | `SECURITY_CHECKLIST.md` heading says exposure is "enforced at startup", but `security.py` ignores `ws_token` and `CORS_origins` | Extend check or correct doc |
| R11 | Med | N bots vs Binance limits, RAM | Section 2 | Load test; cap sessions |
| R12 | Med | Hand-rolled migrations; moving dev base (U2, U4) | `persistence/migrations.py` | Do not alter bot schema; platform tables live in the control-plane DB |
| R13 | Med | Model files are code execution when loaded (U9) | `RISKS_AND_TECH_DEBT.md:17` | Never upload models via UI |

### `.gitignore` in this checkout

**`.env*` is NOT ignored; only exact `.env` is** (`.gitignore:105`). `git check-ignore`: `.env.local` and `.env.production` at root are not ignored, so `SECURITY_CHECKLIST.md:14` is false here. `web/.env*` is covered only by `web/.gitignore:6-7`. Other patterns that collide with this plan:

| Pattern | Now ignores | Fix |
|---|---|---|
| `lib/` (`:42`) | **`web/src/lib/`, which exists and is silently untracked right now**; any `services/*/lib/` | Anchor to Python build dirs (`/lib/`) |
| `config*.json` (`:2`) | New `config_examples/config_*.json` | Add exceptions, as for existing examples |
| `docker-compose-*.yml` (`:120`) | Deploy overlays | Exception, or name differently |
| `user_data/freqaimodels/*` (`:14`) | Custom LSTM/RL model files | Exception for first-party models |

`user_data/strategies/*.py` is not ignored. Generated session configs and DBs stay ignored.

### Strategy editing from the UI conflicts with strategy-as-Python

Strategies are Python classes loaded via importlib (`resolvers/iresolver.py:38`). Editing code from a browser is remote code execution on a host that may hold keys; upstream itself refuses remote strategies (`deps.py:86`, "base64 encoded strategies are not allowed"). It would also sidestep review and change a strategy mid-evaluation.

**Resolution: parameters yes, code no.** Reuse `HyperStrategyMixin` parameter files (`strategy/hyper.py:39,102-106`, JSON next to the strategy file). Each strategy declares bounded `*Parameter`s; the UI validates against that schema. A parameter edit creates a new immutable version and needs a **new session**; it never alters a running one. As the file sits beside the strategy, per-session values need per-session strategy snapshots (section 2). `IslamicSpotStrategy` must first convert its constants. Code changes go through git and review.

### Conflicts between the new spec and constitution / policy

**Watchlist vs filter (executed `screen_pair` for each):** BTC, ETH, BNB, SOL, XRP, DOGE, ADA, LINK and AVAX all return `None`, so **the filter does not reject any of them**. It has no asset denylist at all: only leveraged-token patterns plus a config list, empty in the canonical config. Conflicts are elsewhere:

| # | Conflict | Evidence | Resolution |
|---|---|---|---|
| C1 | **BNB is blacklisted by the canonical config** | `config_islamic_spot.example.json:21-23`. Purpose is probably fee-token accounting, not Sharia [I] | Owner decision. Recommend: allow for paper via overlay; on live, either exclude or disable pay-fees-in-BNB |
| C2 | **Default-allow screening vs fail-closed policy.** No scholar-approved asset list exists; DOGE (speculative/meme) and yield-bearing or exchange-utility tokens are the obvious questions [I: this audit makes no Sharia ruling] | `ISLAMIC_POLICY.md:5,24-26,72` | **Owner/scholar sign-off on the 9 assets before live.** Store as an approved list; recommended: default-deny allowlist for live |
| C3 | L4 gate does not see the config blacklist; docstring implies it does | `order_gate.py:10,38` calls `screen_pair(pair)` with no list; force-entry has no whitelist/blacklist check (`rpc.py:1136-1153`) | Pass the blacklist into L4; keep `force_entry_enable: false` everywhere |
| C4 | Screening false positive | `screen_pair("SYRUP/USDT")` returns "leveraged token" (executed); [I] listed on Binance | Allowlist override if ever wanted; note L4 uses no allowlist, so it stays blocked |
| C5 | RL default has short actions | `ReinforcementLearner.py:106` vs `ISLAMIC_POLICY.md:69` | `LongOnlyRLEnv` on `Base3ActionRLEnv`; fail at start if another env is used |
| C6 | ML before live contradicts ADR-0006 | `DECISIONS.md:71`, `ROADMAP.md:123` | New ADR superseding it (owner's new spec), plus roadmap renumbering |
| C7 | ML needs confidence gating; constitution requires all four validations | `claudeSkills.MD` `# AI Decision Rules`, `ISLAMIC_POLICY.md:53-63` | Implement in `AiRobotBaseStrategy.confirm_trade_entry`; do Phase 7's ADR first |
| C8 | Research paths have no L1 | `enforce_spot_only` only at `worker.py:56`; webserver and backtest bypass by design (`compliance.py:15-17`, `webserver_commands.py:11-12`) | Control plane calls `assert_spot_config` on all generated configs; never offer non-spot |

Spot-only itself does not conflict: nothing in the spec requires futures, margin or shorting. The spec's owner approval matches the live sign-off in `ROADMAP.md:182`; keep both. Telegram being optional is no hard conflict with the constitution's messaging section [I], provided the same reports exist in the UI.

Doc drift to fix in phase 1: `ROADMAP.md:138` still shows Phase 8 `planned` with a different scope.

## 6. Key architecture decisions

| # | Decision | Recommendation |
|---|---|---|
| D1 | Session isolation | One Docker container per session; own SQLite, config, secrets, volume |
| D2 | Bot DB | SQLite per session stays the source of truth; Postgres holds control-plane data and ingested read models. Bot tables have no session key, and per-bot Postgres DBs add load and migration risk for no gain |
| D3 | Market data | Parquet is the OHLCV source of truth; Postgres stores only catalog/coverage, not candles |
| D4 | API | New FastAPI control plane in its own top-level package (e.g. `services/control_plane/`) using `ft_client`; separate process and dependencies. Bot API stays unmodified, private |
| D5 | Web access | Next.js → Nginx → control plane only. Bot credentials never reach the browser |
| D6 | Orchestration | Control plane manages containers through a restricted Docker socket proxy. Compose only for fixed services |
| D7 | Research jobs | One-off CLI containers (`backtesting`, `hyperopt`, `download-data`), results ingested; not webserver mode, which is serial |
| D8 | Strategy interface | `AiRobotBaseStrategy(IStrategy)` with metadata, declared params, `can_short=False`; ML variant adds confidence gating. No parallel strategy abstraction |
| D9 | Strategy changes | UI edits bounded parameters as new immutable versions; code only via git |
| D10 | Live gate | Enforced twice: control-plane approval record **and** engine startup validator (approval reference, `available_capital` ≤ 100, required guards). UI can never set `dry_run: false` alone |
| D11 | Live account | Dedicated Binance sub-account with $100 only, no-withdrawal, IP-locked; exactly one live bot. Keys only in that container |
| D12 | Kill switch | Control-plane action: `/stopentry` + `/forceexit all`, plus persisted halt flag read at startup. Exits never blocked |
| D13 | Python | 3.13 everywhere until 3.14 is proven on the full stack |
| D14 | Compliance list | Owner-approved assets as a versioned file; default-deny on live |
| D15 | Telegram | Central notifier in control plane; bot-level Telegram only for live |

Each needs an ADR in `DECISIONS.md` before its phase, and new core hooks (D10, D12, R6) need the ADR required by ADR-0001. These decisions need the owner: C1, C2, C6.

## 7. Gap list

- **Infra:** own image, compose, Nginx/TLS, backups, Postgres + schema, secrets handling, monitoring
- **Data:** scheduler, catalog, gap detection, Parquet migration
- **Sessions:** supervisor, config generator, port/secret generator, health, snapshots, ingestion
- **Strategies:** base classes, registry, 9 more technical, 5 ML, parameter refactor of the existing one
- **ML:** LSTM model, `LongOnlyRLEnv`, confidence gating, feature/target design, retrain scheduling
- **Evaluation:** report generator, pass criteria, benchmark, downtime accounting, version pinning
- **Governance:** approval workflow, audit log (L6 persistence is deferred, Phase 12), approved assets
- **Live:** validator, stoploss-on-exchange, persistent kill switch, sub-account runbook
- **Compliance hardening:** R6 validator, C3, C5, C8
- **Web:** all screens; auth (single owner, MFA recommended, rate-limited login)
- **Ops:** runbook (Phase 10), upstream sync (Phase 13), `.ai` updates

## 8. Phased plan

One phase at a time, with a `.ai/phases/` record (`PROJECT_RULES.md`). Sizes are rough [I].

| Spec phase | Scope | Exit criteria | Size |
|---|---|---|---|
| **1. Audit** | This document. Fix `.gitignore` (R3), recreate `.venv` (R2), rerun baseline. Owner decides C1, C2, C6; ADRs for D1-D15; roadmap renumbered | Baseline ≤ known failures; `web/src/lib` tracked | S |
| **2. Core infra** | Fork image (R1); compose: Postgres, Nginx, control-plane skeleton; auth; R6 validator; C3 fix; Parquet data job + catalog | Fork image boots; bad configs refused; 9 pairs of Parquet with gap report | M |
| **3. Trading research** | `AiRobotBaseStrategy`, registry, parameter files, 9 technical strategies + refactor of the existing one (10 total); job runner for backtest/hyperopt; lookahead + recursive gate (`optimize/analysis/`) | All 10 pass bias gate; multi-regime backtests stored | L |
| **4. Paper trading** | Supervisor, per-session config/secret generation, kill switch per session, ingestion, restart tests, load test | N sessions run 72 h; `docker restart` and host reboot lose no state; real N documented | L |
| **5. AI/ML** | ADR for Phase 7 first. LightGBM, XGBoost, RandomForest on existing classes; LSTM; `LongOnlyRLEnv`; confidence gating; offline training schedule | 5 models pass bias gate; RAM/CPU per bot measured; short-env guard tested | L |
| **6. Web app** | Dashboard, sessions, trades, strategy + parameter versions, backtests, data status, report, approvals, kill switch. Runs in parallel with 3-5 on the API contract | All actions through control plane; no bot secrets in browser | L |
| **7. Evaluation** | Pre-commit criteria *before* starting; freeze versions; 30 calendar days; generate report | Report covers all sessions with gaps, benchmark and costs. Failing all is a valid outcome | 30 days + S |
| **8. Live** | Live validator, approval, stoploss-on-exchange, sub-account runbook, kill drill, `SECURITY_CHECKLIST.md`, owner + asset sign-off (C2) | Dry drill passes; owner signs explicitly; $100 only, one strategy | M |
| **9. VPS** | Hardening, firewall, TLS, backup + restore test, monitoring, upstream-sync process | Restore tested; external port scan shows only 443 (+ SSH) | M |

**Order note:** deploy VPS foundations before Evaluation in practice, since a 30-day run belongs on the always-on host. Do the hardening part of phase 9 between phases 6 and 7; the live module comes after evaluation.

## 9. Not verified

- 3.14 wheel availability; Binance rate limits; bot memory use; the claim that a running bot writes no candles to disk; `SYRUP` listing; BNB blacklist rationale.
- Full test suite not run (by instruction). `.venv` inspected in the main checkout, because this worktree has none; nothing else outside this checkout was used for findings.
