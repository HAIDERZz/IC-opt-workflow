# C-40 OpenBox Continuation Production Handoff Design

Date: 2026-06-05

## Purpose

C-39 proved that `continue-openbox-real` can continue a real OpenBox/Spectre/OCEAN
run from `100` to `120` cumulative evaluations. C-40 turns that proven path into
a production handoff that an execution agent can follow without relying on
memory or manual command reconstruction.

## Scope

In scope:

- Strengthen generated OpenBox continuation task packets.
- Make the OpenBox execution environment gate visible in the generated handoff.
- Require `finalize-optimizer-run` as the production closeout command in the
  generated task.
- Require supervisor-facing closeout artifacts in the returned artifact list.
- Update the production handoff guide with the first-run and continuation flows.
- Add local packet tests only.

Out of scope:

- Running another real OpenBox/Spectre/OCEAN continuation.
- Changing OpenBox candidate generation or ask-and-tell behavior.
- Changing optimizer objective, constraints, metrics, or formulas.
- Replacing TuRBO or deleting native TuRBO.
- Python PSF parsing.
- OCEAN formula rewriting.
- Adding a daemon, database, scheduler, or broad workflow engine.

## Design

The existing packet renderer remains the single production handoff surface:

```text
hermes-workflow package-optimizer-task PROJECT_DIR --backend openbox --continuation --additional-evals N --cadence-cshrc CADENCE_CSHRC
```

For OpenBox packets, the rendered task must include:

- a toolchain gate command using the known-good OpenBox venv path from
  `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`;
- an execution environment note saying real OpenBox commands run with the
  OpenBox venv first in `PATH`, Cadence cshrc sourced, writable `MPLCONFIGDIR`,
  and non-sandbox/escalated execution;
- the exact `continue-openbox-real` command for continuation packets;
- audit commands including `check-optimizer-run`, `summarize-optimizer-run`,
  and `finalize-optimizer-run`;
- returned artifacts for run evidence, state/ledger, acceptance, completion,
  finalize, insight, and visual reports.

Native TuRBO remains supported and keeps its existing command semantics. The
additional closeout command and returned report artifacts are safe for both
backends because supervisor acceptance already uses `finalize-optimizer-run`.

## Acceptance

- OpenBox continuation packet tests prove the handoff includes the toolchain
  gate, continuation command, finalization command, environment constraints, and
  returned artifacts.
- Existing native TuRBO and OpenBox first-run packet tests continue to pass.
- No real tools run during C-40.
- Progress files and `docs/CURRENT_TASK_STATE.json` are updated.
