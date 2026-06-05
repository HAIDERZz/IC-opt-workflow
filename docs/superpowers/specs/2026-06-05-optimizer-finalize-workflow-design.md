# Optimizer Finalize Workflow Design

Date: 2026-06-05

## Status

Design scope for C-32.

## Context

The optimizer path now has separate supervisor commands:

```text
check-optimizer-run
summarize-optimizer-run
visualize-optimizer-run
```

They are useful, but a production supervisor agent should not have to remember
the exact post-run sequence after an execution agent returns artifacts.

C-32 adds one small finalize command that runs the existing post-run checks in
order and writes a single finalization report.

## Command

```bash
hermes-workflow finalize-optimizer-run PROJECT_DIR
```

Execution order:

```text
check_optimizer_run(project)
-> if accepted: summarize_optimizer_run(project)
-> if summary passes: generate_optimizer_insight_report(project)
-> write reports/optimizer_finalize_report.json
```

## Scope

- Run existing deterministic report commands in one supervisor-side operation.
- Produce a final JSON report pointing to acceptance, completion, and insight
  artifacts.
- Fail closed if acceptance or completion fails.
- Keep generated insight report optional only after acceptance and completion
  are valid.

## Non-Goals

- Do not run Virtuoso, Spectre, OCEAN, SSH, or virtuoso-bridge.
- Do not run optimizer candidate generation.
- Do not change OpenBox or TuRBO.
- Do not parse PSF.
- Do not rewrite OCEAN formulas.
- Do not add a workflow engine, daemon, service, or database.
- Do not replace the existing individual commands.

## Acceptance Criteria

- `finalize-optimizer-run` accepts a valid completed optimizer run and writes:
  - `reports/optimizer_run_acceptance_report.json`
  - `reports/optimizer_completion_report.json`
  - `reports/optimizer_insight_report.json`
  - `reports/optimizer_finalize_report.json`
- The finalize report records the decision, confidence, best observed run id,
  and report paths.
- Rejected optimizer artifacts fail closed after acceptance and do not claim a
  completion decision.
- Existing individual commands remain available.
- No real tools are run in tests.

## Route Audit

- Active top-level direction: lightweight agent workflow around proven tool
  contracts.
- Alignment: C-32 turns existing supervisor checks into a usable post-run
  handoff closeout without changing execution.
- Drift: none intended. This is a wrapper over existing reports, not a new
  optimizer framework.
