# History Warm-Start Design

## Objective

Add an explicit OpenBox history warm-start feature for users who run repeated
optimization rounds on the same IC circuit.

The target workflow is:

1. A user completes an optimization project.
2. The user reads the report and decides to adjust the variable ranges, spec
   thresholds, or FOM/objective expression.
3. The user creates a new project with a new `opt_requirement.md`.
4. The new requirement explicitly references the previous project as a
   warm-start source.
5. The system audits the old history against the current project contract.
6. Accepted historical observations are passed to OpenBox through OpenBox's
   native `History` / `Observation` / `transfer_learning_history` mechanism.

This feature must not change the meaning of continuation. `continue` remains the
same-project path for adding more evaluations when the previous `max_evaluations`
was too small. History warm-start is a new-project path for reusing compatible
history from a previous optimization round.

## Product Decisions

### First-Version Scope

In scope:

- OpenBox real optimization only.
- Local previous project paths only.
- Explicit opt-in from the current project's `opt_requirement.md`.
- Audit report generation before optimizer use.
- Conversion of accepted old points into OpenBox native history objects.
- Current requirement objective and constraints used to re-evaluate old raw
  metric values.

Out of scope:

- TuRBO warm-start.
- fix-run.
- Remote history sources.
- Automatic discovery of old projects.
- Variable name mapping.
- Cross-circuit history transfer.
- User-defined blacklist logic.
- Custom surrogate or optimizer behavior outside OpenBox.
- Modifying an old project's `requirement.md` and continuing inside the same
  project.

### Compatibility Contract

The first version is deliberately strict.

- Current and previous project variable name sets must be exactly identical.
- Variable ranges, candidate values, or bounds may differ.
- A historical point whose parameter values fall outside the current variable
  space is rejected as `out_of_current_space`.
- Metric/OCEAN extraction definitions must be equivalent between the current and
  previous project.
- Objective/FOM and constraint results from the previous project are not reused.
- Objective/FOM and constraints are recalculated from the previous project's raw
  metric values using the current project's `metrics.yaml`.
- Observations missing required raw metrics are rejected.
- Observations with invalid numeric values are rejected.
- Observations from failed or incomplete runs are rejected.
- Complete observations that become `constraint_failed` under the current
  requirement may still enter OpenBox history because they contain valid raw
  metrics and valid constraint residuals.

The purpose of this strict contract is to make the first implementation useful
for same-circuit iteration while avoiding ambiguous cross-project reuse.

## Requirement Entry

Add a top-level requirement block:

```yaml
history_warm_start:
  enabled: true
  sources:
    - path: /path/to/previous_project
      label: mixer_nf12_round1
  max_observations: 200
  warm_start_strategy: topk
```

Field semantics:

- `enabled`: Required to affect optimization. Missing block or `enabled: false`
  means no optimizer behavior change.
- `sources`: Local previous project paths. First version supports one or more
  local paths.
- `path`: Absolute or current-project-relative path to a previous project.
- `label`: Optional display label for reports. It does not participate in
  compatibility matching.
- `max_observations`: Optional deterministic cap for accepted observations
  passed to OpenBox. If omitted, use all accepted observations. If a cap is
  applied, sort accepted observations by current recomputed objective, then by
  source order, then by source evaluation index.
- `warm_start_strategy`: Optional OpenBox warm-start strategy. First version
  defaults to `topk` and passes the value through to OpenBox when supported.

The requirement parser should render this block into a structured config file so
later CLI steps do not need to re-parse Markdown prose.

## Audit Artifacts

Generate:

```text
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
```

The JSON report is the stable machine-readable contract. The Markdown report is
for users and agents.

Required JSON fields:

```json
{
  "schema_version": "1.0",
  "enabled": true,
  "status": "completed",
  "sources": [
    {
      "label": "mixer_nf12_round1",
      "path": "/path/to/previous_project",
      "status": "accepted",
      "candidate_trace_count": 80,
      "accepted_observation_count": 37,
      "rejected_observation_count": 43,
      "rejection_reasons": {
        "out_of_current_space": 16,
        "missing_required_metric": 10,
        "failed_or_incomplete_run": 17
      }
    }
  ],
  "compatibility": {
    "variable_set": "matched",
    "metric_definitions": "matched",
    "backend": "openbox_real"
  },
  "accepted_observation_count": 37,
  "rejected_observation_count": 43,
  "openbox_transfer_learning": {
    "enabled": true,
    "source_count": 1,
    "accepted_observation_count": 37,
    "warm_start_strategy": "topk",
    "applied_to_advisor": true
  },
  "issues": []
}
```

Rejection reason names are part of the contract:

- `source_path_missing`
- `source_not_valid_project`
- `missing_optimizer_evaluations`
- `unsupported_backend`
- `variable_set_mismatch`
- `metric_definition_mismatch`
- `missing_required_metric`
- `out_of_current_space`
- `invalid_numeric_value`
- `failed_or_incomplete_run`
- `history_object_rejected_by_openbox`

If no accepted observations remain, the audit status is still `completed`, the
optimizer starts without transfer history, and the report includes a warning.
Warm-start is an enhancement, not a default blocker for normal optimization.

## Data Flow

### Existing Flow

The current OpenBox real flow is:

```text
run_openbox_real_optimization()
  -> assert_valid_project()
  -> _load_continuation_traces() only when continue_from_existing=True
  -> _run_openbox_batches()
  -> _create_advisor()
  -> _prepare_unique_batch()
  -> evaluator()
  -> _trace_from_observation()
  -> _make_openbox_observation()
  -> _update_observations()
  -> write_openbox_reports()
```

### New Flow

The new warm-start path is inserted before creating the real OpenBox advisor:

```text
run_openbox_real_optimization()
  -> assert_valid_project()
  -> resolve history_warm_start config
  -> build history_warm_start_audit
  -> _run_openbox_batches(..., warm_start_audit=...)
  -> _create_advisor(..., transfer_learning_history=...)
```

Continuation replay remains separate:

```text
continue_from_existing=True
  -> current-project prior traces only
  -> no external history warm-start
```

The first version rejects mixed use of external warm-start and continuation.
If `continue_from_existing=True` and `history_warm_start.enabled=true`, fail with
a clear message explaining that continuation is for same-project budget extension
and warm-start is for a new project referencing old history.

## History Reader

The primary source is the previous project's:

```text
reports/optimizer_evaluations.jsonl
```

Each row is expected to contain at least:

- `parameters`
- `metrics`
- `status`
- `objective`
- `issues`
- `evaluation_index`
- `run_id`

The reader should be tolerant of individual bad rows and should count them as
rejected observations. A malformed source file rejects that source and records a
source-level issue.

The reader must not use the old row's `objective` as the current objective. It
may use old objective/status fields only for reporting and diagnostics.

## Compatibility Checks

### Variable Check

Compare current and previous variable names after loading structured project
configuration. The sets must match exactly.

If the source project's variable config has extra or missing variable names, the
entire source is rejected as `variable_set_mismatch`.

Historical parameter dictionaries must also have exactly the current variable
names. A row with extra or missing parameter keys is rejected as
`variable_set_mismatch` even if the source project's variable config matches.

Then validate each parameter value against the current variable's allowed space.
Rows outside the current space are rejected as `out_of_current_space`.

### Metric/OCEAN Definition Check

Compare current and previous metric extraction definitions from structured
artifacts, not raw Markdown prose.

The implementation should compare the stable fields that determine raw metric
meaning, including metric name, testbench/corner association, extraction
expression, units when present, and waveform/scalar extraction mode when present.

If a required current metric is absent in the previous definition, reject the
source as `metric_definition_mismatch`.

If definitions differ for a required current metric, reject the source as
`metric_definition_mismatch`.

### Objective and Constraint Re-Evaluation

For each row with complete raw metrics, call the existing objective evaluation
logic against the current contract. The intended production helper is the current
`evaluate_candidate_objective(metrics_config, optimizer_config, metrics)` path.

Accepted rows should preserve:

- current objective value
- current FOM value
- current constraint residuals
- original source path / run id / evaluation index for audit traceability

This keeps spec changes meaningful. A previous run can be feasible or infeasible
under the new requirement depending on current thresholds and formulas.

## OpenBox Integration

The OpenBox adapter should construct native OpenBox history objects only after
the audit has accepted rows.

Expected integration shape:

1. Build the same current OpenBox config space used for the new project.
2. For each accepted row, create a current-space `Configuration` from the row's
   parameters.
3. Create an OpenBox `Observation` with:
   - `objectives=[current_objective]`
   - `constraints=current_constraint_residuals`
   - `extra_info` containing source path, run id, evaluation index, and audit
     status.
4. Add observations to an OpenBox `History` for the source project.
5. Pass the resulting histories to `Advisor(... transfer_learning_history=...)`.
6. Pass through the configured OpenBox `warm_start_strategy` when supported.

The adapter must not implement custom search behavior. OpenBox decides how the
history affects suggestions.

When tests provide `advisor_factory`, do not require real OpenBox `History`
objects. The fake advisor path should remain lightweight and can assert the
audited transfer-history payload separately.

## Reporting Integration

The final OpenBox report should link the audit:

```json
{
  "openbox": {
    "history_warm_start": {
      "enabled": true,
      "audit": "reports/history_warm_start_audit.json",
      "accepted_observation_count": 37,
      "applied_to_advisor": true,
      "warm_start_strategy": "topk"
    }
  }
}
```

The later HTML optimization report should consume this JSON as a fixed section.
That report work is separate from this feature's first implementation.

## Error Handling

Default behavior is non-blocking unless the user mixes incompatible modes.

- Missing block: no behavior change.
- `enabled: false`: no behavior change.
- Bad source path: source rejected, optimization continues.
- Invalid previous project: source rejected, optimization continues.
- Missing history file: source rejected, optimization continues.
- Variable mismatch: source rejected, optimization continues.
- Metric definition mismatch: source rejected, optimization continues.
- Individual bad row: row rejected, source continues.
- Zero accepted rows: warning, optimization starts from zero.
- OpenBox rejects a constructed observation: row rejected as
  `history_object_rejected_by_openbox`; other rows continue.
- `continue_from_existing=True` with enabled warm-start: fail fast with a clear
  message.

## Testing Strategy

Use generic factory projects and synthetic optimizer-evaluation rows. Do not run
Spectre in unit tests.

Required tests:

- Requirement intake parses `history_warm_start`.
- No block means existing OpenBox behavior and reports are unchanged.
- `enabled: false` means no transfer history.
- Matching variable set passes.
- Extra old variable in source config rejects the source as mismatch.
- Missing old variable in source config rejects the source as mismatch.
- Extra or missing variable in an individual history row rejects that row as
  mismatch.
- Out-of-current-space row is rejected as `out_of_current_space`.
- Matching metric definition passes.
- Different metric extraction definition rejects as `metric_definition_mismatch`.
- Missing required metric rejects row as `missing_required_metric`.
- Invalid numeric metric rejects row as `invalid_numeric_value`.
- Failed/incomplete run rejects row as `failed_or_incomplete_run`.
- Current objective and constraints are recalculated from raw metrics.
- Constraint-failed observations with complete metrics can enter OpenBox history.
- Audit with zero accepted rows does not fail the optimizer.
- Enabled warm-start passes transfer history to real OpenBox advisor construction.
- Fake `advisor_factory` tests do not need real OpenBox `History` objects.
- Enabled warm-start plus `continue_from_existing=True` fails clearly.

## Implementation Phases

### Phase 1: Audit Foundation

- Add requirement schema/config rendering.
- Add history source reader.
- Add variable compatibility check.
- Add metric definition compatibility check.
- Add row-level acceptance/rejection logic.
- Add JSON and Markdown audit reports.
- Do not yet alter OpenBox advisor behavior.

### Phase 2: OpenBox Adapter

- Convert accepted audit rows into OpenBox `History` / `Observation`.
- Pass histories into `Advisor`.
- Record applied status in OpenBox reports.
- Preserve fake advisor tests without requiring OpenBox internals.

### Phase 3: Docs and User Workflow

- Update requirement README and examples.
- Update user guide and agent skill docs.
- Document that continuation and history warm-start are different workflows.
- Add a short troubleshooting section for zero accepted observations.

## Risks

- Metric definition comparison can be too strict or too loose. The first version
  should prefer false negatives over unsafe reuse.
- Some old projects may lack enough raw metric detail. Those rows must be
  rejected rather than inferred.
- OpenBox transfer-learning behavior may vary by surrogate type. The report must
  state the resolved strategy and whether transfer history was actually applied.
- Combining continuation and external history would be confusing. Keep the modes
  mutually exclusive for the first version.

## Success Criteria

- A new project can reference a previous same-circuit project and receive a clear
  audit report.
- The audit identifies accepted and rejected observations with deterministic
  reasons.
- Accepted observations are passed into OpenBox through native OpenBox history
  objects.
- Existing projects without `history_warm_start` behave exactly as before.
- `continue` behavior is unchanged.
- Full unit tests and lint pass.
