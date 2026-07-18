# Task / Phase Template

> Copy to `.ai/phases/phase-<n>-<slug>.md` before starting a phase. Fill every section —
> "n/a" must be justified. The filled file is the permanent phase record.

```markdown
# Phase <n> — <title>

Status: planned | in-progress | done | dropped
Started: <date>   Finished: <date>

## Goal
<one paragraph — what exists after this phase that didn't before>

## Reason
<why now; which constitution/roadmap requirement it serves>

## Compliance check (mandatory)
- Touches order placement / leverage / shorting / pair selection / funding?  yes|no
- If yes: enforcement layers involved (L1–L6) and how fail-closed is preserved:
- Uncertainty? If any → STOP, reject, escalate.

## Design
<approach; alternatives considered; link ADR if one was written>

## Files affected
<exact list; mark upstream files vs. new modules>

## Expected result
<observable behavior, config surface, messages>

## Risk
<what can break; likelihood; blast radius; mitigations>

## Rollback plan
<exact steps to undo: revert commit / config flag / module removal>

## Testing requirements
<unit / integration / regression / dry-run evidence needed to call it done>

## Documentation updates
<which .ai/ files and user docs change>

## Review
- [ ] REVIEW_CHECKLIST.md passed
- Reviewer notes:

## Outcome
<what actually happened; deviations from plan; follow-ups created>
```
