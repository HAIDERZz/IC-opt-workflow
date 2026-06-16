# Execution Package Preflight Readiness Design

## Goal

Align the execution package, preflight reports, and first-run approval gate with the current Plan C route: Hermes owns deterministic preflight, while the execution agent owns Maestro export and post-approval real execution.

## Problem

Plan C C-1 and C-2 moved safe netlist preparation and dry-run rendering into Hermes commands:

- `hermes-workflow prepare-netlist`
- `hermes-workflow dry-run`

The remaining package and approval text still reflects the older route in a few places:

- `EXECUTION_TASK.md` tells the execution agent to write `reports/netlist_preparation_report.json` and `reports/dry_run_report.json`.
- `approve` requires `state/health_check.json`, but there is no Hermes command that creates the pre-approval health report after C-2.
- Some user-facing CLI help and approval reason text still says "Claude preflight reports" even though Hermes now owns deterministic preflight reports.

C-3 fixes this contract mismatch without implementing real Spectre execution.

## Scope

Included:

- Update generated `EXECUTION_TASK.md` so the execution agent exports or places `netlists/exported/input.scs`, then stops before preflight and real execution.
- Add a Hermes-side preflight health writer that creates `state/health_check.json` before first approval.
- Add a CLI command named `preflight-health`.
- Keep `execution_manifest.json` required preflight report paths unchanged:
  - `reports/netlist_preparation_report.json`
  - `reports/dry_run_report.json`
  - `state/health_check.json`
- Update approval wording and CLI help from Claude-specific preflight language to generic Hermes/preflight language.
- Add tests for package text, health report writing, approval success after the new preflight sequence, and approval rejection when pre-approval real-run artifacts exist.
- Update progress, overview, and resume docs.

Excluded:

- Running Virtuoso.
- Running Spectre.
- Implementing Maestro export automation.
- Implementing real metric extraction.
- Implementing a real optimizer loop.
- Changing the existing report schemas unless a failing test proves a schema issue.
- Changing `mock-run` behavior.

## Current Route

The intended pre-approval flow is:

```text
Hermes validate
Hermes package
Execution agent exports or places netlists/exported/input.scs
Hermes prepare-netlist
Hermes dry-run
Hermes preflight-health
Hermes approve
Execution agent may run the first real Spectre batch only after approve_first_real_run
```

The package step remains before Maestro export because `EXECUTION_TASK.md` is what tells the execution agent which testbench to export and which setup changes are forbidden.

## Execution Task Contract

`EXECUTION_TASK.md` should no longer tell the execution agent to write Hermes-owned preflight reports.

It should say the execution agent must:

- Use `virtuoso-bridge-lite` skills only for tool-side actions.
- Inspect or export the configured Maestro testbench.
- Produce or place the exported deck at `netlists/exported/input.scs`.
- Preserve Maestro setup: analyses, model includes, simulator options, save options, corners, constraints, objective, variable bounds, and variable steps.
- Not template variables directly.
- Not write `reports/netlist_preparation_report.json`.
- Not write `reports/dry_run_report.json`.
- Not write `state/health_check.json` for preflight readiness.
- Stop and wait for Hermes to run deterministic preflight and approval before any real Spectre execution.

It should say Hermes will run:

```bash
hermes-workflow prepare-netlist PROJECT_DIR
hermes-workflow dry-run PROJECT_DIR
hermes-workflow preflight-health PROJECT_DIR
hermes-workflow approve PROJECT_DIR
```

The task document may still mention expected preflight report paths as Hermes-owned artifacts.

## Preflight Health Contract

Add a focused module, `src/hermes_workflow/health.py`, with:

```python
write_preflight_health(project_dir: Path) -> HealthCheck
```

The command writes `state/health_check.json`.

Healthy pre-approval payload:

```json
{
  "schema_version": "1.0",
  "status": "healthy",
  "real_run_started": false,
  "current_evaluations": 0,
  "best_candidate_path": null,
  "last_batch_id": null,
  "issues": []
}
```

The function should validate the project config through `assert_valid_project(project_dir)` before writing the report.

The function should fail closed if it detects real-run artifacts before first approval. For C-3, these artifacts are:

- `ledger/experiment_ledger.jsonl`
- `state/optimizer_state.json`
- `state/best_candidate.json`

If any are present, the function writes:

- `status: "error"`
- `real_run_started: true`
- `current_evaluations: 0`
- `best_candidate_path: "state/best_candidate.json"` if that file exists, otherwise `null`
- `last_batch_id: null`
- `issues` listing the detected artifact paths

This lets the existing approval gate reject the project through `load_preflight_reports()`.

The preflight health writer must not delete or modify any existing optimizer artifacts.

## CLI Contract

Add:

```bash
hermes-workflow preflight-health PROJECT_DIR
```

Success output:

```text
preflight health passed
```

Failure output:

```text
preflight health failed
<issue lines>
report: state/health_check.json
```

The command exits with code 1 on failure and must not print tracebacks for expected domain errors.

Update existing CLI help:

- `approve` should say "Project directory with Hermes preflight reports" or "Project directory with preflight reports", not "Claude preflight reports".

## Approval Contract

`decide_first_real_run()` should keep its existing gate structure:

1. Execution manifest exists.
2. Execution manifest has immutable config hashes.
3. Config validation passes.
4. Preflight reports are ready.

Only the human-readable approval reason should change from Claude-specific language to:

```text
config validation and preflight reports passed
```

No approval logic should be weakened.

## Error Handling

- Missing `state/health_check.json` remains an approval-time error surfaced through the existing CLI error boundary.
- `preflight-health` writes a health report whenever the project config can be loaded.
- If project config validation fails, `preflight-health` exits with code 1 through the existing CLI domain-error pattern and does not fabricate a healthy report.
- If real-run artifacts are present, `preflight-health` writes an error health report and exits with code 1.

## Testing

Add or update tests for:

- Generated `EXECUTION_TASK.md` says the execution agent exports `netlists/exported/input.scs`.
- Generated `EXECUTION_TASK.md` does not instruct the execution agent to write netlist preparation, dry-run, or health preflight reports.
- `write_preflight_health(project_dir)` writes the healthy payload.
- `preflight-health` CLI writes `state/health_check.json` and prints `preflight health passed`.
- Existing `approve` succeeds after:
  - `init`
  - `package`
  - write sanitized `template.scs` or run existing helper path that produces preflight pass reports
  - `dry-run`
  - `preflight-health`
- `preflight-health` writes an error report and exits 1 if pre-approval real-run artifacts exist.
- `approve` rejects when the health report says `real_run_started: true`.
- Full test suite passes.
- `ruff check .` passes.

Tests must not run Virtuoso, Spectre, network access, Claude CLI, or real optimizer execution.

## Documentation

Update:

- `README.md` command sequence.
- `docs/PROJECT_WORKFLOW_OVERVIEW.md`.
- `docs/EXECUTION_PROGRESS_2026-05-29.md`.
- `docs/COMPACT_RESUME_CHECKPOINT.md`.

The docs should make the responsibility split explicit:

- Execution agent: export or place `input.scs`.
- Hermes: prepare netlist, dry-run, preflight health, package, approval.
- Execution agent: first real run only after `approve_first_real_run`.

## Acceptance Criteria

- Generated execution tasks no longer assign Hermes deterministic preflight report writing to the execution agent.
- `hermes-workflow preflight-health PROJECT_DIR` exists.
- A complete pre-approval file-contract flow can produce all three required preflight reports without Spectre, Virtuoso, or optimizer execution.
- `hermes-workflow approve PROJECT_DIR` can approve that flow.
- Approval still rejects any health report indicating real execution started before approval.
- Full tests and ruff pass.
