# C-43 Optimizer Status Command Design

Date: 2026-06-05

## Purpose

Add a small supervisor-facing command that summarizes an optimizer project after
the existing closeout reports are available. The command should reduce the need
to manually open acceptance, completion, finalize, and insight reports.

## Scope

In scope:

- Add `hermes-workflow optimizer-status PROJECT_DIR`.
- Reuse existing closeout logic by calling `finalize-optimizer-run` behavior.
- Print concise human-readable status:
  - finalization status;
  - decision and confidence;
  - `global_optimum_claim`;
  - best observed run id;
  - evaluation count;
  - status counts;
  - continuation recommendation and reason;
  - key report paths.

Out of scope:

- Running OpenBox, TuRBO, Spectre, OCEAN, Virtuoso, SSH, or bridge commands.
- Creating a new optimizer report contract.
- Changing optimizer objective, constraints, candidate generation, acceptance,
  completion, finalization, insight generation, or metric formulas.
- Python PSF parsing or OCEAN formula rewriting.

## Design

Create `src/hermes_workflow/optimizer_status.py` as a thin adapter around
`finalize_optimizer_run`. It reads the completion report that finalization
already writes and returns a compact dataclass. The CLI formats that dataclass
into stable plain text.

The command intentionally does not introduce a new JSON report. Supervisor
agents should continue using existing machine-readable reports for structured
data:

```text
reports/optimizer_run_acceptance_report.json
reports/optimizer_completion_report.json
reports/optimizer_finalize_report.json
reports/optimizer_insight_report.json
```

## Acceptance

- `optimizer-status` passes on an accepted fake optimizer project.
- Output includes decision, confidence, global optimum claim, best observed,
  evaluation count, status counts, continuation recommendation, and report paths.
- A rejected optimizer project exits non-zero and prints finalize issues through
  the existing fail-closed behavior.
- No real tools run.
