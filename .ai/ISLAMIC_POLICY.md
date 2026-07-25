# Islamic Trading Policy — Sharia Compliance

> Binding policy. Derived from the constitution ([SKILLS.md](SKILLS.md)).
> When any implementation choice conflicts with this document, the implementation is
> rejected. When compliance is *uncertain*, the trade or feature is rejected.

## 1. Rules

**Forbidden (haram) — must be impossible, not merely disabled:**
- Futures / perpetual contracts
- Margin trading
- Leverage (> 1.0 in any form)
- Short selling
- Borrowing of any asset
- Interest (riba) in any form
- Funding-rate payments or receipts
- Leveraged tokens (e.g. `*UP/*DOWN`, `*3L/*3S`, `*BULL/*BEAR`)

**Allowed (halal):**
- Spot trading of owned assets only
- Real asset exchange (delivery-settled spot)
- Risk management (stoploss, position limits, circuit breakers)

**Additionally screened:** the tradable pair universe must exclude instruments that are
structurally interest-bearing or synthetic (leveraged tokens); a configurable
asset blacklist supports scholar-guided exclusions.

## 2. Enforcement model — defense in depth

A single config value (`trading_mode: spot`) is *not* sufficient assurance: config can be
edited, defaulted wrongly, or bypassed by a strategy. Compliance must be enforced at
every layer, and each layer must assume the others may fail.

| Layer | Enforcement | Where (verified) |
|---|---|---|
| **L1 Config** | **IMPLEMENTED (Phase 1):** `freqtrade.islamic.enforce_spot_only()` called from the trading entry point (`Worker._init`) rejects any non-spot config — live and dry-run — and arms the enforcement marker. | `freqtrade/islamic/compliance.py`, hook in `freqtrade/worker.py` |
| **L2 Exchange** | **IMPLEMENTED (Phase 1):** `assert_spot_operation()` at the top of `_set_leverage` and `set_margin_mode` raises on an armed bot before any dry-run early-return — those operations are unreachable in a trading process. | `freqtrade/islamic/compliance.py`, hooks in `exchange/exchange.py` |
| **L3 Strategy** | `can_short` must be False (upstream default); `leverage()` callback must return 1.0; loader rejects strategies that declare otherwise. | `strategy/interface.py:88`, `freqtradebot.py:1153-1171` (SPOT already forces 1.0) |
| **L4 Order gate** | Pre-order compliance validation in `confirm_trade_entry` chain: pair not on haram blacklist, side is long, leverage is 1.0, order is spot. Uncertain ⇒ reject and log why. | `freqtradebot.py:932` (entry veto point) |
| **L5 Pair universe** | **IMPLEMENTED (Phase 2):** `IslamicComplianceFilter` removes leveraged tokens (`BTCUP`/`BTC3L`/`ETHBULL` …) and blacklisted assets from the whitelist; screening logic in `freqtrade/islamic/screening.py`. | `freqtrade/plugins/pairlist/IslamicComplianceFilter.py` |
| **L6 Audit** | Every compliance rejection is logged and emitted as an RPC message (Telegram + API) with the reason. | `RPCMessageType` extension, `rpc/` |

Upstream behavior that already supports this (verified):
- SPOT mode blocks short signals (`strategy/interface.py:1376-1382`).
- SPOT mode hard-forces leverage 1.0 (`freqtradebot.py:1171`).
- SPOT mode returns 0.0 funding fees and no liquidation price
  (`exchange.py:3981`, `:4007`).
- Margin interest code (`freqtrade/leverage/interest.py`) is unreachable in SPOT mode.

Our work (Roadmap Phase 1+) converts "unreachable by configuration" into
"impossible by construction", plus screening and audit.

## 3. AI decision rule

AI (FreqAI models or any future LLM/advisor component) **never** places orders.
AI output is a *recommendation* that must pass, in order:

1. Market validation (data fresh, spread/liquidity sane)
2. Risk validation (limits, drawdown, cooldowns — see risk section of ROADMAP)
3. Islamic validation (L4 gate above)
4. Confidence threshold (below threshold ⇒ no trade)

Only then may the engine execute — through its normal, fully validated entry path.

## 4. Non-negotiables for reviewers

- No PR may add code paths that set leverage, open shorts, call margin/futures ccxt
  endpoints, or compute interest — even "dead" or "for future use".
- FreqAI RL action spaces including short actions must not be wired into live trading.
- Any new exchange integration must be verified spot-capable and delivery-settled.
- The compliance guard modules themselves require the strictest review + test coverage.
- When in doubt: **reject**. Escalate to the project owner for scholar consultation.
