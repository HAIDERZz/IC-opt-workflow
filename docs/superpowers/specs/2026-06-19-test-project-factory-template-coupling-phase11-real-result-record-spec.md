# Test Project Factory Template Coupling Phase 11 Spec

Date: 2026-06-19

## Objective

Decouple `tests/test_real_result_record.py` from direct packaged-template project
creation while preserving the real-result recording contract and its CLI helper
compatibility.

This phase targets the local `_create_ready_project()` setup and the old
inverter-specific ledger, metric, and parameter fixtures in
`tests/test_real_result_record.py`. The file should keep exporting
`_create_ready_project()` and `_write_valid_checked_result()` because
`tests/test_cli.py` imports them for record-real-result CLI coverage.

## Scope

Allowed files to modify:

- `tests/test_real_result_record.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed files to read for orientation:

- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `tests/test_cli.py`
- `src/hermes_workflow/real_result_record.py`
- `src/hermes_workflow/mock_optimizer.py`

No other production, test, release, prompt, plan, graph, or generated-output
files may be modified unless the implementation discovers a real blocker and
stops for review first.

## Requirements

### 1. Direct Template Call Removal

`tests/test_real_result_record.py` must stop importing and calling
`create_project_from_template()`.

Required behavior:

- Replace `_create_ready_project()` setup with `create_approved_generic_project()`
  from `tests/project_factory.py`, followed by `prepare_real_run()`.
- Preserve the public helper names used by `tests/test_cli.py`:
  - `_create_ready_project`
  - `_write_valid_checked_result`
- Remove `TEMPLATE_TEXT`.
- Remove direct package helpers that become unnecessary after switching to the
  approved generic factory path (`build_execution_package`,
  `decide_first_real_run`, `write_pass_reports`) unless a concrete failing test
  proves they are still needed.
- Keep `sha256_file`, because fake metric-result manifests still need request
  and script hashes.

The migrated target file must not contain these old packaged-template tokens:

- `create_project_from_template`
- `bridge_test_inv`
- `FN`
- `WN`
- `FP`
- `WP`
- `TEMPLATE_TEXT`
- `rise`
- `fall`
- `DC`

Do not replace the old inverter fixture with a hardcoded Mixer fixture or any
other circuit-specific fixture. Derive names and values from generated artifacts
or use neutral schema-only names in pure model tests.

### 2. Generic Candidate and Metric Derivation

Project-backed tests must derive runtime names from generated files:

- Candidate parameters from
  `runs/real/real_001/candidate.json`.
- Metric names and request metadata from
  `runs/real/real_001/metric_extraction_request.json`.

Recommended helper shape:

- `_candidate_parameters(project_dir) -> dict[str, str]`
- `_metric_names(project_dir) -> tuple[str, str]`
- `_metric_values(project_dir, *, objective_value: float, constraint_value: float) -> dict[str, float]`
- `_objective_cost(project_dir, values) -> float`

For the generic factory defaults:

- The first metric is the objective metric.
- The second metric is the constrained metric.
- The objective expression is `<first_metric> - <second_metric>`.
- The objective direction is `maximize`, so `record_real_result()` stores the
  negated objective as cost.
- The default feasible constrained metric value should remain below `1e-3`.
- Constraint-failing cases should set the constrained metric to a value above
  `1e-3`.

### 3. Behavior Preservation

Preserve the existing coverage:

- `LedgerRow` accepts real-result provenance.
- `LedgerRow` still accepts legacy mock payload shape, but with neutral parameter
  and metric names instead of old template names.
- `LedgerRow` rejects invalid real statuses.
- `RealResultRecordReport` schema accepts pass reports.
- Missing `result_manifest.json` fails without optimizer writes.
- Missing metric result manifest fails without optimizer writes.
- A valid checked result writes ledger, optimizer state, best candidate, and
  record report.
- Duplicate run and duplicate candidate detection prevent append.
- Invalid ledger prevents append and state writes.
- Constraint-failing real result writes a ledger row but does not update best.
- Worse feasible real result preserves existing best.
- Best candidate can be derived from existing ledger.
- Infeasible existing best does not block a feasible real result.
- Stale best file is replaced by ledger best.
- Invalid best file is repaired from ledger.
- Stale best file is removed when no feasible ledger best exists.
- Maximize objective normalization is still asserted with a negative stored
  objective cost.

Do not weaken exact assertions into broad shape checks. Replace old exact names
with derived exact names and keep exact list/dict/objective assertions where the
current tests have them.

### 4. CLI Consumer Compatibility

`tests/test_cli.py` imports helpers from `tests/test_real_result_record.py`.
Do not edit `tests/test_cli.py` in Phase 11.

Required verification:

- `tests/test_real_result_record.py` passes alone.
- `tests/test_real_result_record.py tests/test_cli.py` passes together.
- The CLI tests that import `_create_ready_project()` and
  `_write_valid_checked_result()` keep their existing stdout/path assertions.

If `tests/test_cli.py` fails in a way that requires editing it, stop and report
the dependency issue instead of widening scope.

### 5. Coupling Guard

Remove this file from `ALLOWED_TEMPLATE_CALLERS`:

- `tests/test_real_result_record.py`

The allowlist count should shrink from 10 to 9.

### 6. Inventory

Update `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`:

- Change the phase list to include Phase 11.
- Add a `Phase 11 status` section before Phase 10.
- State that `tests/test_real_result_record.py` was migrated.
- State that the allowlist changed from 10 to 9.
- Remove `tests/test_real_result_record.py` from the remaining migration waves.
- Add exact verification results after running the commands in this spec.

## Non-Goals

Do not modify:

- Production code under `src/`
- `tests/project_factory.py`
- `tests/test_project_factory.py`
- `tests/test_cli.py`
- `tests/real_run_smoke_helpers.py`
- Backend implementation files
- Remote implementation files
- Release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`
- Existing specs/plans/prompts

Do not commit, tag, push, or publish. The user will ask separately when this
phase should be committed.

## Required Verification

Run these commands from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_real_result_record.py tests/test_cli.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py tests/test_run_retention.py tests/test_optimizer_progress_state.py tests/test_fix_run_flow.py tests/test_multi_testbench_aggregation.py tests/test_real_result_record.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP\|TEMPLATE_TEXT\|rise\|fall\|DC" tests/test_real_result_record.py || true
grep -R --exclude-dir=__pycache__ -n "from tests.test_real_result_record\|tests.test_real_result_record" tests || true
```

Expected baseline before migration:

- `tests/test_real_result_record.py`: `21 passed`
- Consumer group (`tests/test_real_result_record.py`, `tests/test_cli.py`):
  `70 passed, 13 warnings`
- Release checkout: clean

Expected after migration:

- `tests/test_real_result_record.py`: `21 passed`
- Guard: `1 passed`
- Target plus guard: `22 passed`
- Consumer group: `70 passed, 13 warnings`
- Phase 1-11 regression group: about `372 passed, 13 warnings`
- Full suite: about `1194 passed, 13 warnings`
- Ruff passes
- `git diff --check` is clean
- Release checkout remains clean
- Drift grep over `tests/test_real_result_record.py` prints no matches
- Cross-import grep prints only `tests/test_cli.py` source-level imports plus any
  incidental tool output formatting. The guard entry should be gone.

If any count differs because a prior phase changed collection counts, record the
real count and explain the reason in the final report.

## Stop Conditions

Stop and report instead of widening scope if:

- A production-code change appears necessary.
- `tests/project_factory.py` needs another behavior change.
- Any test outside the three allowed files must be edited.
- `tests/test_cli.py` fails in a way that requires editing it.
- Full-suite failures appear outside the touched surface and cannot be tied
  directly to this migration.
