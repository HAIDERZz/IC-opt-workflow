# Dry-Run Candidate Renderer Design

## Goal

Add a Hermes-side dry-run step that renders one deterministic candidate deck from `netlists/templates/template.scs`, checks placeholder and mock metric contracts, and writes `reports/dry_run_report.json` without running Spectre, Virtuoso, or the optimizer loop.

## Scope

Included:

- A deterministic dry-run candidate renderer.
- Reading the validated project YAML bundle.
- Reading `netlists/templates/template.scs`.
- Rendering approved placeholders into `runs/dry_run/input.scs`.
- Writing `reports/dry_run_report.json` using the existing `DryRunReport` schema.
- Checking unresolved placeholders and unexpected template variables.
- Checking mock metrics, objective evaluation, and constraints using existing Plan B helpers.
- Verifying that dry-run ledger and state paths are writable without writing real optimizer artifacts.
- A CLI command named `dry-run`.
- Unit and CLI tests with sanitized inline fixtures.

Excluded:

- Running Spectre.
- Running Virtuoso.
- Running `run_mock_optimization()`.
- Writing real optimizer ledger rows, best-candidate files, or optimizer state.
- Parsing Spectre result files.
- Parsing Maestro calculator formulas.
- Supporting user-selected candidate values in this first dry-run renderer.
- Committing real `input.scs` examples.

## Architecture

Add a focused module, `src/hermes_workflow/dry_run.py`, that owns dry-run candidate rendering and `DryRunReport` writing.

The module will:

1. Validate and load the project contract through `assert_valid_project()`.
2. Read `netlists/templates/template.scs` from `project_config.yaml`.
3. Build a deterministic candidate from `variables.yaml`.
4. Replace `{{VARIABLE_NAME}}` placeholders with candidate values.
5. Check rendered placeholder state.
6. Compute mock metrics, constraints, and objective through existing Plan B helper functions.
7. Probe `ledger/` and `state/` directory writability without creating production optimizer artifacts.
8. Write `runs/dry_run/input.scs`.
9. Write `reports/dry_run_report.json`.

`cli.py` will expose this through:

```bash
hermes-workflow dry-run PROJECT_DIR
```

The dry-run renderer is a preflight check. It produces enough evidence for the existing approval gate to reason about dry-run readiness, but it does not advance optimizer state.

## Deterministic Candidate Contract

The first dry-run candidate uses each variable's configured lower bound:

```json
{
  "FN": "2",
  "WN": "0.3 um",
  "FP": "2",
  "WP": "0.3 um"
}
```

This keeps dry-run output stable, reviewable, and easy to reproduce. It also avoids duplicating Plan B's sampling policy inside dry-run rendering.

Integer variables use `lower` exactly as written after validation. Continuous variables use `lower` exactly as written after validation, including whitespace and unit suffixes.

## Placeholder Contract

C-2 consumes the placeholder syntax established by C-1:

```text
{{VARIABLE_NAME}}
```

Rules:

- Every approved variable from `variables.yaml` must appear at least once in the template.
- Every approved placeholder occurrence is replaced by the dry-run candidate value.
- Any remaining `{{...}}` after rendering is an unresolved placeholder.
- Any placeholder name that is not declared in `variables.yaml` is an unexpected template variable.
- A dry run fails closed if unresolved or unexpected placeholders exist.

The renderer does not use a general template engine. It performs explicit placeholder replacement for approved variable names and scans the result for remaining `{{...}}` tokens.

## DryRunReport Contract

The step writes the existing report model:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "rendered_candidate_scs": "runs/dry_run/input.scs",
  "placeholder_check": {
    "unresolved_placeholders": [],
    "unexpected_template_variables": []
  },
  "metrics_import_ok": true,
  "mock_metrics_ok": true,
  "objective_ok": true,
  "constraints_ok": true,
  "ledger_write_ok": true,
  "state_write_ok": true,
  "issues": []
}
```

`metrics_import_ok` means the dry-run module could import the existing mock metric helpers.

`mock_metrics_ok` means mock metrics were computed for the deterministic candidate.

`objective_ok` means the configured objective expression evaluated successfully against the mock metrics.

`constraints_ok` means configured constraints were evaluated successfully. Constraint pass or fail is not itself a dry-run failure; the dry run checks whether the contract can be evaluated.

`ledger_write_ok` and `state_write_ok` mean the project-local `ledger/` and `state/` directories can be created or accessed. C-2 must not append an optimizer ledger row or write optimizer state files.

## Failure Behavior

The renderer should write `reports/dry_run_report.json` whenever it can load enough project context to locate `reports/`.

Fail conditions:

- Project YAML contract is invalid.
- `template.scs` is missing.
- An approved variable placeholder is missing from the template.
- The template contains an unexpected placeholder.
- The rendered deck still contains unresolved placeholders.
- Mock metric helper import fails.
- Mock metrics cannot be computed.
- Objective expression evaluation fails.
- Constraint evaluation raises an error.
- The rendered deck cannot be written.
- `ledger/` or `state/` writability check fails.

On fail:

- `status` is `fail`.
- All completed checks keep their actual boolean values.
- Failed checks are false.
- `issues` contains human-readable messages.
- A partially written rendered candidate should be removed if the final report status is fail.

## Data Flow

1. C-1 creates `netlists/templates/template.scs`.
2. C-2 builds a lower-bound dry-run candidate from `variables.yaml`.
3. C-2 renders `runs/dry_run/input.scs`.
4. C-2 checks placeholders.
5. C-2 computes mock metrics, objective, and constraints.
6. C-2 writes `reports/dry_run_report.json`.
7. Existing preflight report loading and approval logic consume the dry-run report unchanged.

## CLI Contract

Add:

```bash
hermes-workflow dry-run PROJECT_DIR
```

Success output:

```text
dry run passed
```

Failure output:

```text
dry run failed
<issue lines>
report: reports/dry_run_report.json
```

The command exits with code 1 on failure and must not print tracebacks for expected domain errors.

## Testing

Tests should live in `tests/test_dry_run.py` and `tests/test_cli.py`.

Required coverage:

- Successful lower-bound candidate rendering from `template.scs`.
- Rendered candidate deck contains concrete values and no `{{...}}` placeholders.
- `DryRunReport` validates with the existing model.
- Missing `template.scs` writes a fail report.
- Missing approved placeholder writes a fail report.
- Unexpected placeholder writes a fail report.
- Mock metrics, objective, constraints, ledger writability, and state writability pass in the success case.
- Failure removes any stale `runs/dry_run/input.scs`.
- CLI success smoke.
- CLI failure smoke without traceback.

No test may run Spectre, Virtuoso, Claude CLI, network access, or the real optimizer loop. No test may depend on real `input.scs` examples.

## Acceptance Criteria

- `run_dry_run(project_dir)` writes `runs/dry_run/input.scs` and `reports/dry_run_report.json` on success.
- `run_dry_run(project_dir)` writes a fail `dry_run_report.json` on expected contract failures.
- The existing `DryRunReport` schema is unchanged.
- `hermes-workflow dry-run PROJECT_DIR` is available.
- Full test suite passes.
- `ruff check .` passes.
- The feature does not start a real Spectre run, real Virtuoso action, or optimizer loop.
