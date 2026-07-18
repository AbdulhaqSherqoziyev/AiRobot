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
