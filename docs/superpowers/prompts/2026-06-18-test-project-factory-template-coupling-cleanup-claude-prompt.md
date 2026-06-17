# Claude Prompt: Test Project Factory and Template Coupling Cleanup

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

## Current state

There are already uncommitted changes in this dev checkout:

- `src/hermes_workflow/optimizer_flow.py`
- `tests/test_optimizer_flow.py`
- `docs/ARCHITECTURE_MAP_CN.md`
- prior optimizer validation risk spec/plan/prompt/report

The optimizer validation risk fix has already been verified:

```text
PYTHONPATH=src .venv/bin/python -m pytest tests/test_optimizer_flow.py tests/test_product_cli.py -q
-> 29 passed, 13 warnings

PYTHONPATH=src .venv/bin/python -m pytest -q
-> 1193 passed, 13 warnings

PYTHONPATH=src .venv/bin/python -m ruff check src tests
-> All checks passed!

git diff --check
-> clean
```

Do not revert or rewrite those changes unless a test failure directly requires a compatible adjustment.

Do not touch:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1
graphify-out/
```

Do not commit, tag, push, or publish.

## Goal

Execute Phase 1 of the Test Project Factory and Template Coupling Cleanup:

- Keep `create_project_from_template()` as the product/template API.
- Add a generic test-only project factory.
- Add tests for the factory.
- Add a template-coupling guard with an explicit allowlist.
- Migrate the first low-risk behavior tests away from direct `create_project_from_template()` usage.
- Leave large backend/remote/adapter migrations for later waves.

This is not a product behavior change.

## Required reading

Read these files first:

```text
docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-cleanup-spec.md
docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-cleanup-plan.md
docs/ARCHITECTURE_MAP_CN.md
docs/superpowers/reports/2026-06-18-optimizer-flow-validation-risk-report.md
```

## Use graphify and codegraph

Use graphify only as a read-only map. Do not rebuild the graph.

Run:

```bash
graphify explain "create_project_from_template()"
```

Use codegraph to confirm the call surface:

```bash
codegraph_callers create_project_from_template
codegraph_node create_project_from_template file=package.py includeCode=true
```

Use source grep to get the concrete migration inventory:

```bash
rg -n "create_project_from_template" tests src docs -g '!graphify-out/**'
rg -l "create_project_from_template" tests | sort
rg -n "bridge_test_inv|FN|WN|FP|WP|NF_3G|VB_LO|create_project_from_template" tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_mock_optimizer.py tests/test_real_result_record.py tests/test_remote_optimizer_flow.py tests/test_optimizer_task_package.py tests/test_approvals.py
```

## Implementation boundaries

Create:

```text
tests/project_factory.py
tests/test_project_factory.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Modify only if needed for Phase 1:

```text
tests/report_helpers.py
tests/test_health.py
tests/test_optimizer_flow.py
tests/test_metric_results.py
tests/test_next_real_run.py
tests/test_real_run.py
tests/test_result_handoff.py
tests/test_real_run_recovery.py
```

Optional, only if simple and low-risk:

```text
tests/test_approvals.py
```

Do not migrate these in Phase 1 unless the plan explicitly becomes impossible without doing so:

```text
tests/test_optimizer_task_package.py
tests/test_run_retention.py
tests/test_remote_optimizer_flow.py
tests/test_remote_fix_run_flow.py
tests/test_spectre_ocean_adapter.py
tests/test_remote_spectre_ocean.py
tests/test_openbox_backend.py
tests/test_native_turbo.py
tests/test_mock_optimizer.py
```

Keep `tests/test_package.py` template-based.

## Important implementation rules

1. `tests/project_factory.py` must not call `create_project_from_template()`.
2. The default generic project must not use:
   - `bridge_test_inv`
   - `FN`, `WN`, `FP`, `WP`
   - `rise`, `fall`, `DC`
   - Mixer-specific names such as `NF_3G`, `VB_LO`
3. The default project should use neutral names like:
   - project: `generic_project`
   - variables: `VAR_INT`, `VAR_WIDTH`
   - metrics: `metric_gain`, `metric_power`
4. `tests/test_template_coupling_guard.py` should start with a permissive allowlist and shrink as files are migrated.
5. If a migrated file still needs circuit-specific variables for the behavior being tested, do not force it into the first wave. Leave it for later and record it in the inventory report.
6. Do not hide migration failures by weakening production validation.
7. Do not update release examples/templates in this task.

## Verification commands

Run these and report exact results:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_project_factory.py -q
PYTHONPATH=src .venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_metric_results.py \
  tests/test_next_real_run.py \
  tests/test_real_run.py \
  tests/test_result_handoff.py \
  tests/test_real_run_recovery.py \
  -q
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m ruff check src tests
git diff --check
git status --short
```

Also verify the release checkout was not touched:

```bash
git -C /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1 status --short
```

## Final report format

Create or update the inventory report:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Then respond with:

```text
Files created:
- tests/project_factory.py
- tests/test_project_factory.py
- tests/test_template_coupling_guard.py
- docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md

Files migrated:
- <list actual migrated files>

Still intentionally template-based:
- tests/test_package.py
- tests/test_cli.py if still applicable

Remaining migration waves:
- <grouped list from inventory>

Verification:
- <command>: <exact result>
- <command>: <exact result>
- <command>: <exact result>

Notes:
- optimizer validation fix preserved
- release checkout not touched
- graphify-out not touched/staged
- no commits/tags/pushes performed
```

Do not claim all template coupling is removed after Phase 1. Claim only that the generic factory, guard, inventory, and first migration wave are complete.
