# Project Rules — Development Workflow

> Operational rules for every working session. The constitution is
> [SKILLS.md](SKILLS.md); architecture constraints are in
> [ARCHITECTURE_RULES.md](ARCHITECTURE_RULES.md).

## 1. The cycle (never skip steps)

Understand → Analyze → Document → Design → Plan → Implement → Test → Review → Optimize.
If a step is skipped, stop and state why.

## 2. Phase discipline

- All work is organized as phases in [ROADMAP.md](ROADMAP.md).
- Exactly **one phase in flight** at a time. A phase is *done* only when: implemented,
  tested (per its stated testing requirements), reviewed against
  [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md), and documentation updated.
- Each phase starts from [TASK_TEMPLATE.md](TASK_TEMPLATE.md); the filled template is
  kept in `.ai/phases/` as the phase record.
- Phases are small. If a phase grows, split it.

## 3. Documentation-first

- Architecture changes: update `.ai/ARCHITECTURE.md` (and user docs if user-facing)
  **before or with** the code, never after "when there's time".
- Significant decisions get an ADR entry in [DECISIONS.md](DECISIONS.md).
- `.ai/` is the single source of truth for internal engineering knowledge. If code and
  `.ai/` disagree, fix one of them immediately.

## 4. Change hygiene

- One logical change at a time; small commits; never touch files unnecessarily.
- Never delete existing features unless explicitly requested.
- Never commit secrets; API keys/tokens only via environment variables.
- Large or irreversible changes require explicit owner confirmation first.

## 5. Compliance gate (always on)

Before designing any feature, answer in writing (in the phase record):
- Does this touch order placement, leverage, shorting, pair selection, or funding?
- If yes: which ISLAMIC_POLICY.md enforcement layers does it interact with, and how is
  fail-closed behavior preserved?
- If compliance is uncertain: **stop and reject**; escalate to the owner.

## 6. Definition of Done (every phase)

- [ ] Code merged, small and reviewed
- [ ] Tests written and passing (`pytest`), CI green
- [ ] Lint/type checks pass (ruff / mypy per repo config)
- [ ] Dry-run behavior verified for engine-touching changes
- [ ] `.ai/` docs updated (architecture, roadmap status, ADRs)
- [ ] Logging explains *why* for every new decision path
- [ ] Rollback plan from the phase record is still valid

## 7. Working style

- Never guess about library or API behavior — read the code or docs first.
- Search for existing reusable code before writing new code.
- Challenge bad ideas, including the owner's; propose the safer alternative.
- Prefer the safest design over the fastest or most profitable one.
