# Architecture Decision Records (ADR log)

> Append-only. One entry per significant decision. Statuses:
> proposed | accepted | superseded-by-ADR-n.
> Format: Context → Decision → Consequences. Keep entries short.

---

## ADR-0001 — Extend upstream Freqtrade via native extension points; do not fork core
- **Status:** accepted (2026-07-18)
- **Context:** We build on Freqtrade `2026.7-dev`. Upstream moves fast (exchange API
  fixes, ccxt bumps). Heavy core edits would end merge-ability and orphan us on a dev
  snapshot. Verified extension surface: IResolver-loaded classes (strategies,
  pairlists, protections, FreqAI models, exchanges), strategy lifecycle callbacks,
  RPCHandler registration, RPCMessageType events, KeyValueStore/CustomData.
- **Decision:** All platform features use these extension points. Core files may only
  receive tiny, marked hook lines, each with its own ADR. New first-party code lives
  in a dedicated package (working name `freqtrade/islamic/`) and `user_data/`.
- **Consequences:** Slightly more indirection; upstream merges stay cheap; hook
  inventory must be maintained (see Phase 13).

## ADR-0002 — Sharia compliance enforced by layered hard guards, not configuration
- **Status:** accepted (2026-07-18)
- **Context:** Upstream SPOT mode already blocks shorts (`strategy/interface.py:1376`),
  forces leverage 1.0 (`freqtradebot.py:1171`), and skips funding/liquidation logic.
  But this is a *config value*, editable in one line, and haram code paths remain
  present and callable.
- **Decision:** Implement defense-in-depth layers L1–L6 (see ISLAMIC_POLICY.md):
  config rejection, exchange-level assertion, strategy constraints, pre-order gate,
  pair screening, audit trail. Guards fail closed; entries only, never exits.
- **Consequences:** Some redundancy by design; compliance survives config mistakes,
  strategy bugs, and upstream drift; small hooks needed in config validation,
  exchange init, and execute_entry (Phases 1–3).

## ADR-0003 — AI is advisory only; execution stays in the validated engine path
- **Status:** accepted (2026-07-18)
- **Context:** Constitution: "AI never directly buys or sells." FreqAI already fits
  this shape — predictions become dataframe signals that pass normal engine
  validation; it never places orders itself.
- **Decision:** All AI (FreqAI now, any future advisor) produces recommendations that
  must pass market → risk → Islamic → confidence validation before the engine's
  normal entry path may act. RL short-action environments are never wired to live
  trading. Details designed in Phase 7's dedicated ADR.
- **Consequences:** Slower to add flashy AI features; every AI decision is auditable
  and gated; a bad model cannot bypass risk or compliance.

## ADR-0004 — `.ai/` is the internal source of truth; `claudeSkills.MD` is constitution
- **Status:** accepted (2026-07-18)
- **Context:** Long-lived project, multiple future contributors (human and AI).
- **Decision:** Engineering knowledge lives in `.ai/` (index: README.md there).
  `claudeSkills.MD` at repo root is the constitution; `.ai/SKILLS.md` mirrors it and
  the root file wins on divergence. Docs update before or with code, never after.
- **Consequences:** Documentation discipline is enforced by review checklist; drift is
  tracked as risk P4.

## ADR-0005 — Pairlist compliance filter lives in `plugins/pairlist/`, logic in `islamic/`
- **Status:** accepted (2026-07-19)
- **Context:** Phase 2 needs a Sharia screening filter loadable by name in the
  `pairlists` config chain. Freqtrade's `PairListResolver` discovers handlers in
  `freqtrade/plugins/pairlist/` and `user_data/pairlists/`, and the config schema
  validates `method` against `AVAILABLE_PAIRLISTS` (`constants.py`).
- **Decision:** The thin `IPairList` adapter (`IslamicComplianceFilter`) lives in
  `freqtrade/plugins/pairlist/` (idiomatic, resolver-discoverable, additive new
  file). The reusable screening logic lives in `freqtrade/islamic/screening.py`
  (pure functions, unit-tested, reusable by the Phase 3 pre-order gate). One
  additive line registers the name in `AVAILABLE_PAIRLISTS` (marked hook).
- **Consequences:** Compliance logic stays cohesive in `freqtrade/islamic/`; the
  filter is a first-class, config-selectable handler; only a one-line upstream edit
  (the enum) is needed, tracked for merges.

## ADR-0006 — First live path uses a simple rule-based strategy; AI deferred
- **Status:** accepted (2026-07-26)
- **Context:** The platform vision is AI-powered, but the first live path needs a
  transparent, low-risk, quickly-validated strategy. Owner chose "simple rule-based
  first, AI later".
- **Decision:** Ship `IslamicSpotStrategy` (user_data/strategies) — a conservative,
  long-only, trend-following spot strategy (EMA regime + RSI pullback + ADX/volume
  confirmation; conservative ROI/stoploss/trailing). Roadmap Stage C (FreqAI, P7–P9)
  is deferred until after the first simple-strategy live pilot. FreqAI RL short
  action spaces remain out of scope (ISLAMIC_POLICY.md).
- **Consequences:** Faster, explainable path to a first pilot; the AI advisor layer
  becomes a later increment layered on the same validated engine + guards.

## ADR-0007 — Quant Lab platform lives in `quantlab/` with its own engines
- **Status:** accepted (2026-11-04)
- **Context:** The owner's platform spec asks for many isolated $100 paper sessions that survive
  restarts, an internal paper engine independent of exchange APIs, and a separate live module.
  The audit (D1) recommended one Freqtrade container per session. That means about one process
  and its RAM per session, and it could not be built or tested here without Docker access.
- **Decision:** A new top-level package, `quantlab/`, holds the data, strategy, backtest, paper,
  ML, optimizer, risk, evaluation and live engines, the FastAPI control plane and workers.
  One candle-by-candle core is shared by backtest and paper. Freqtrade stays untouched and
  runnable; `quantlab` reuses its compliance screening (`freqtrade/islamic/screening.py`).
- **Consequences:** Sessions are database rows, so 15 sessions cost no extra processes. Isolation
  is enforced by per-session portfolios and tested. The cost: `quantlab` does not inherit
  Freqtrade's order handling, protections or L1-L6 hooks, so its live engine is new, unproven
  code. It has been tested against a fake exchange only. This supersedes audit decisions D1, D2,
  D4 (`ft_client`), D6, D7 and D8.

## ADR-0008 — Live trading gates
- **Status:** accepted (2026-11-04)
- **Decision:** Real orders need all of: final evaluation report, strategy passed it, owner
  authorization with exact text and password, stored key that passes a rights check (no
  withdrawal, margin or derivatives; IP restricted), `QL_LIVE_ENABLED=true`, the `live` worker
  running, and an owner Start action. First allocation is capped at 100 USDT in code. Orders are
  written to the database before sending. An unknown outcome halts until reconciled. The kill switch
  commits its halt before touching the exchange and needs no password. Stop-loss is enforced
  by the engine every cycle, so it does not run if the worker is down; an exchange-side stop is
  not implemented.

## ADR-0009 — ML strategies before live (proposed: owner decision needed)
- **Status:** proposed (2026-11-04)
- **Context:** The owner's spec includes ML strategies in the evaluation. ADR-0006 deferred AI
  for the first live path, and the constitution treats AI as advisory (ADR-0003).
- **Current behaviour:** ML strategies trade only on paper unless their model was explicitly promoted
  and attached. The authorization code does not exclude them from live; if the owner keeps ADR-0006,
  that restriction still has to be added.
