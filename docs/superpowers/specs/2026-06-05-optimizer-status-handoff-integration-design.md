# C-44 Optimizer Status Handoff Integration Design

Date: 2026-06-05

## Purpose

Make the C-43 `optimizer-status` command part of the standard optimizer
handoff closeout so supervisor agents consistently read one concise status
summary after execution-agent runs.

## Scope

In scope:

- Add `hermes-workflow optimizer-status PROJECT_DIR` to generated optimizer task
  packet audit commands.
- Mention the command in `OPTIMIZER_EXECUTION_TASK.md` and required returned
  artifacts expectations.
- Update `docs/OPTIMIZER_PRODUCTION_HANDOFF_GUIDE.md` so supervisor closeout
  runs `finalize-optimizer-run` followed by `optimizer-status`.

Out of scope:

- Running real OpenBox, TuRBO, Spectre, OCEAN, Virtuoso, SSH, or bridge commands.
- Changing optimizer execution, acceptance, completion, finalize, or insight
  semantics.
- Adding a new report contract.
- Python PSF parsing or OCEAN formula rewriting.

## Design

Keep `finalize-optimizer-run` as the machine acceptance gate. Add
`optimizer-status` as a supervisor readability layer after finalization.

Generated task packets should list audit commands in this order:

```text
check-optimizer-run
summarize-optimizer-run
finalize-optimizer-run
optimizer-status
```

The command does not create required raw tool artifacts. It reads existing
reports and prints the concise supervisor summary.

## Acceptance

- Native TuRBO and OpenBox task packet tests prove `optimizer-status` is present
  in generated task text and manifest audit commands.
- Production handoff guide documents the command as the final human-readable
  closeout step.
- No real tools run.
