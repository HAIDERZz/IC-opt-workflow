# Post-Approval Real-Run Execution Contract Design

## Goal

Add a Hermes-side post-approval command that prepares the first real Spectre run package after `approve_first_real_run`, without invoking Spectre, Virtuoso, or the optimizer loop.

## Problem

Plan C C-1 through C-3 now define the safe pre-approval route:

```text
Execution agent exports netlists/exported/input.scs
Hermes prepare-netlist
Hermes dry-run
Hermes preflight-health
Hermes approve
```

After `approve`, the workflow still has a gap: there is no deterministic file-contract handoff for the first real run. If the execution agent proceeds directly from `supervisor_instruction.json` to a shell command, it may invent a run directory layout, skip config hash checks, render candidate decks inconsistently, or blur the boundary between approved setup and real execution.

C-4 closes that gap by preparing a real-run package that is safe to inspect and hand to a future Spectre runner. It does not run Spectre.

## Scope

Included:

- A post-approval guard that requires `supervisor_instruction.json` to contain `decision: "approve_first_real_run"`.
- A config drift guard that verifies current immutable config hashes against `execution_package/execution_manifest.json`.
- A deterministic first real candidate package generated from `netlists/templates/template.scs`.
- Rendering all approved variable placeholders into `runs/real/<run_id>/input.scs`.
- Writing `runs/real/<run_id>/candidate.json`.
- Writing `runs/real/<run_id>/real_run_manifest.json`.
- A CLI command named `prepare-real-run`.
- Unit and CLI tests with sanitized fixtures.
- Documentation and resume-state updates.

Excluded:

- Running Spectre.
- Running Virtuoso.
- Launching shell subprocesses for simulator execution.
- Parsing Spectre result files.
- Computing real metrics.
- Appending production ledger rows.
- Writing `state/optimizer_state.json` or `state/best_candidate.json`.
- Implementing a full optimizer loop.
- Supporting arbitrary user-selected candidate values in C-4.
- Committing real `input.scs` examples.

## Current Route

C-4 extends the workflow after approval:

```text
Hermes approve
supervisor_instruction.json says approve_first_real_run
Hermes prepare-real-run
runs/real/real_001/input.scs
runs/real/real_001/candidate.json
runs/real/real_001/real_run_manifest.json
future Spectre runner consumes the package
```

The command is intentionally one step before execution. It creates all files needed for a future runner to invoke Spectre, but it does not invoke the simulator.

## Architecture

Add a focused module:

```text
src/hermes_workflow/real_run.py
```

The module owns post-approval real-run package creation. It should follow the existing pattern used by `dry_run.py`, `health.py`, and `package.py`: business logic lives in a module, while `cli.py` formats success or expected failure output.

Public API:

```python
prepare_real_run(project_dir: Path, *, run_id: str | None = None) -> RealRunPackage
```

`run_id` defaults to `real_001` for C-4. If a caller supplies a run ID, it must match:

```text
real_[0-9]{3}
```

The implementation should:

1. Validate and load the project bundle with `assert_valid_project(project_dir)`.
2. Load `execution_package/execution_manifest.json`.
3. Load `supervisor_instruction.json`.
4. Require the supervisor decision to be `approve_first_real_run`.
5. Verify current config hashes match manifest `immutable_config_files`.
6. Verify `netlists/templates/template.scs` exists.
7. Build the deterministic first real candidate from `variables.yaml`.
8. Render placeholders into `runs/real/<run_id>/input.scs`.
9. Fail if any `{{...}}` placeholders remain.
10. Write `candidate.json`.
11. Write `real_run_manifest.json`.
12. Return a small result object with paths and manifest payload.

## Candidate Contract

C-4 uses the lower-bound candidate, matching C-2 dry-run:

```json
{
  "FN": "2",
  "WN": "0.3 um",
  "FP": "2",
  "WP": "0.3 um"
}
```

This keeps the first post-approval package deterministic and easy to review. Optimizer-driven candidate selection is deferred to a later plan.

`candidate.json` should be:

```json
{
  "schema_version": "1.0",
  "candidate_id": "real_001",
  "source": "lower_bound_first_real_run",
  "parameters": {
    "FN": "2",
    "WN": "0.3 um",
    "FP": "2",
    "WP": "0.3 um"
  }
}
```

The candidate parameters are strings, preserving the same value formatting used in `variables.yaml`.

## Real-Run Manifest Contract

`real_run_manifest.json` should be written next to the rendered deck:

```json
{
  "schema_version": "1.0",
  "run_id": "real_001",
  "project_name": "bridge_test_inv",
  "created_at_utc": "2026-05-31T00:00:00Z",
  "status": "prepared",
  "supervisor_decision": "approve_first_real_run",
  "template_scs": "netlists/templates/template.scs",
  "rendered_input_scs": "runs/real/real_001/input.scs",
  "candidate_file": "runs/real/real_001/candidate.json",
  "candidate_id": "real_001",
  "candidate_source": "lower_bound_first_real_run",
  "approved_config_hashes": {
    "config/project_config.yaml": "<sha256>",
    "config/variables.yaml": "<sha256>",
    "config/metrics.yaml": "<sha256>",
    "config/spectre.yaml": "<sha256>",
    "config/optimizer.yaml": "<sha256>"
  },
  "template_sha256": "<sha256>",
  "rendered_input_sha256": "<sha256>",
  "spectre": {
    "engine": "spectre_x",
    "preset": "ax",
    "output_format": "psfascii",
    "parallel_jobs": 10,
    "timeout_s": 3600
  },
  "forbidden_actions": [
    "modify_maestro_setup",
    "modify_immutable_config_files",
    "change_variable_bounds",
    "change_objective_or_constraints"
  ]
}
```

`created_at_utc` should use the same UTC ISO format used elsewhere in the project, with `Z` suffix and no microseconds.

`status` is `prepared`. C-4 must not introduce `running`, `passed`, or `failed` statuses because it does not execute Spectre.

## Approval Guard

`prepare_real_run()` must reject unless `supervisor_instruction.json` exists and contains:

```json
{
  "decision": "approve_first_real_run"
}
```

Expected rejection messages:

- Missing instruction: `supervisor instruction is missing`
- Malformed instruction JSON: `supervisor instruction is invalid`
- Wrong decision: `first real run is not approved`
- Missing or empty approved hashes: `supervisor instruction is missing approved_config_hashes`

The instruction must contain a non-empty `approved_config_hashes` object. Those hashes must match the manifest hashes. A missing, empty, or mismatched object is a hard failure.

The function should not call `decide_first_real_run()` itself. Approval is an explicit previous workflow step.

## Config Drift Guard

C-4 should reuse the same immutable config file list used by `build_execution_package()`.

For each manifest entry in `immutable_config_files`, compute the current SHA-256 of the project file and compare it with the approved hash.

If any file is missing or changed, fail before writing the run directory:

```text
immutable config drift detected: config/variables.yaml
```

If `execution_manifest.json` is missing or malformed, fail before writing the run directory.

## Template Rendering Contract

C-4 consumes the C-1 placeholder syntax:

```text
{{VARIABLE_NAME}}
```

Rules:

- Every approved variable from `variables.yaml` must have a value in the candidate.
- Every placeholder matching an approved variable is replaced.
- Any remaining `{{...}}` after replacement is a failure.
- Unexpected placeholders are a failure.
- Rendering does not use a general template engine.
- Rendering must not mutate `netlists/templates/template.scs`.

The rendered deck path is:

```text
runs/real/<run_id>/input.scs
```

If package creation fails after creating the run directory, C-4 should remove the partial `runs/real/<run_id>/` directory so the command can be retried.

If `runs/real/<run_id>/real_run_manifest.json` already exists, C-4 should refuse to overwrite the existing package.

## CLI Contract

Add:

```bash
hermes-workflow prepare-real-run PROJECT_DIR
```

Optional argument:

```bash
hermes-workflow prepare-real-run PROJECT_DIR --run-id real_001
```

Success output:

```text
real run package prepared
run: runs/real/real_001
manifest: runs/real/real_001/real_run_manifest.json
```

Expected failure output:

```text
Error: first real run is not approved
```

The command exits with code 1 on expected domain errors and must not print tracebacks for expected failures.

## Data Flow

1. C-3 writes `supervisor_instruction.json` through `hermes-workflow approve`.
2. C-4 reads the instruction and verifies approval.
3. C-4 reads `execution_package/execution_manifest.json`.
4. C-4 verifies immutable config hashes.
5. C-4 reads `netlists/templates/template.scs`.
6. C-4 builds the lower-bound candidate from `variables.yaml`.
7. C-4 renders `runs/real/real_001/input.scs`.
8. C-4 writes `candidate.json`.
9. C-4 writes `real_run_manifest.json`.
10. A later plan may pass this package to a Spectre runner.

## Error Handling

Fail before writing files when:

- Project config validation fails.
- `execution_manifest.json` is missing.
- `execution_manifest.json` is malformed.
- `supervisor_instruction.json` is missing.
- `supervisor_instruction.json` is malformed.
- Supervisor decision is not `approve_first_real_run`.
- Approved config hashes are missing or empty.
- Current config hash differs from approved hash.
- `template.scs` is missing.
- Run ID is invalid.
- Existing `real_run_manifest.json` would be overwritten.

Fail with cleanup when:

- Placeholder rendering leaves unresolved placeholders.
- Candidate file writing fails.
- Rendered deck writing fails.
- Manifest writing fails.

Expected failures should use `ValueError`, `FileNotFoundError`, `FileExistsError`, or a focused project exception if implementation finds that cleaner. CLI should translate those into code 1 without traceback.

## Testing

Tests should live in:

```text
tests/test_real_run.py
tests/test_cli.py
```

Required unit coverage:

- `prepare_real_run()` rejects missing `supervisor_instruction.json`.
- `prepare_real_run()` rejects `reject_first_real_run`.
- `prepare_real_run()` rejects changed immutable config after approval.
- `prepare_real_run()` rejects missing `execution_manifest.json`.
- `prepare_real_run()` rejects missing `template.scs`.
- `prepare_real_run()` creates `runs/real/real_001/input.scs`.
- Rendered real deck contains lower-bound values and no `{{...}}` placeholders.
- `candidate.json` records `candidate_id`, `source`, and parameter strings.
- `real_run_manifest.json` records run paths, hashes, approved config hashes, and Spectre policy.
- Existing `real_run_manifest.json` is not overwritten.
- Partial run directory is cleaned up after a simulated write failure.

Required CLI coverage:

- `hermes-workflow prepare-real-run PROJECT_DIR` succeeds after the full preflight approval flow.
- CLI success output includes the run directory and manifest path.
- CLI rejection for missing approval exits 1 without traceback.
- CLI rejection for config drift exits 1 without traceback.

Tests must not run Spectre, Virtuoso, Claude CLI, network access, or a real optimizer loop. Tests must not depend on local-only real `input.scs` examples.

## Documentation

Update:

- `README.md` command sequence.
- `docs/PROJECT_WORKFLOW_OVERVIEW.md` workflow diagram and module list.
- `docs/EXECUTION_PROGRESS_2026-05-29.md`.
- `docs/COMPACT_RESUME_CHECKPOINT.md`.
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`.

Docs should make the boundary explicit:

- `prepare-real-run` prepares a run package after approval.
- It does not execute Spectre.
- A later plan will consume the package for simulator execution and real metric extraction.

## Acceptance Criteria

- `hermes-workflow prepare-real-run PROJECT_DIR` exists.
- The command refuses to prepare a package before `approve_first_real_run`.
- The command refuses to prepare a package after immutable config drift.
- The command creates `runs/real/real_001/input.scs`, `candidate.json`, and `real_run_manifest.json` after approval.
- The rendered deck has no unresolved placeholders.
- The manifest records candidate identity, paths, hashes, approved config hashes, and Spectre policy.
- The command does not run Spectre, Virtuoso, subprocesses, or optimizer execution.
- Existing real-run packages are not silently overwritten.
- Full test suite passes.
- `ruff check .` passes.

## Deferred Work

The following are intentionally left for later plans:

- Optional Spectre subprocess runner.
- Real Spectre result parsing.
- Metric extraction from Spectre outputs.
- Production ledger rows for real runs.
- Optimizer-driven candidate generation.
- Batch execution.
- Multi-corner execution.
