# .ai/ — Engineering Workspace & Single Source of Truth

Internal documentation for the AI-assisted Islamic Spot Trading Platform built on
Freqtrade (`2026.7-dev` baseline). Start here.

## Reading order for a new contributor (human or AI)

1. [MASTER_PROMPT.md](MASTER_PROMPT.md) — the mission and standing orders
2. [SKILLS.md](SKILLS.md) — the constitution (mirror of repo-root `claudeSkills.MD`)
3. [ISLAMIC_POLICY.md](ISLAMIC_POLICY.md) — Sharia rules + layered enforcement model
4. [ARCHITECTURE.md](ARCHITECTURE.md) — how the codebase actually works (verified)
5. [ARCHITECTURE_RULES.md](ARCHITECTURE_RULES.md) — how we're allowed to change it
6. [ROADMAP.md](ROADMAP.md) — phased plan; one phase in flight at a time

## Working documents

| File | Purpose |
|---|---|
| [PROJECT_RULES.md](PROJECT_RULES.md) | Development workflow, phase discipline, Definition of Done |
| [CODING_STANDARDS.md](CODING_STANDARDS.md) | Style, design, and code rules |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Test pyramid, compliance test requirements |
| [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md) | Mandatory pre-merge gate |
| [TASK_TEMPLATE.md](TASK_TEMPLATE.md) | Template copied into `phases/` per phase |
| [DECISIONS.md](DECISIONS.md) | ADR log (append-only) |
| [RISKS_AND_TECH_DEBT.md](RISKS_AND_TECH_DEBT.md) | Living risk & debt register |
| `phases/` | One record per executed roadmap phase |

## Ground rules (summary)

- Sharia compliance is non-negotiable; uncertain ⇒ reject (ISLAMIC_POLICY.md).
- Extend upstream via its extension points; never fork core logic (ADR-0001).
- AI recommends; the validated engine executes (ADR-0003).
- Docs change before or with code. If code and `.ai/` disagree, fix it now.
- One roadmap phase at a time: plan → implement → test → review → document.
