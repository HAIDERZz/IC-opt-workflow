# Claude Prompt: Test Project Factory Template Coupling Cleanup Phase 2

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is the dev repo. Do not touch the release checkout:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1
```

## Objective

Execute Phase 2 of the test project factory/template coupling cleanup.

Migrate exactly these two tests away from direct packaged-template fixture usage:

```text
tests/test_result_handoff.py
tests/test_metric_results.py
```

Then shrink the guard allowlist and update the inventory report.

## Required Reading

Read these files before editing:

```text
docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-phase2-spec.md
docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-phase2-plan.md
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
tests/project_factory.py
tests/test_template_coupling_guard.py
tests/test_result_handoff.py
tests/test_metric_results.py
```

Also inspect the Phase 1 baseline if needed:

```text
docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-cleanup-spec.md
docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-cleanup-plan.md
```

## Tooling Guidance

Use codegraph and graphify if available.

Recommended first checks:

```text
codegraph explore:
tests/test_result_handoff.py tests/test_metric_results.py create_approved_generic_project prepare_real_run check_real_run check_metric_results
```

For graphify, query the existing graph to confirm that this phase is only reducing
test coupling around `create_project_from_template()` and is not a product runtime
refactor.

Do not rely on graph output alone. Read the source files directly before editing.

## Strict Scope

You may modify only:

```text
tests/test_result_handoff.py
tests/test_metric_results.py
tests/test_template_coupling_guard.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify production files under `src/`.

Do not modify release files under `../ic-auto-opt-workflow-v0.1`.

Do not touch, stage, delete, or rewrite:

```text
graphify-out/
```

Do not commit, tag, push, or publish. Report results only.

## Implementation Requirements

### 1. Guard first

Remove these files from `ALLOWED_TEMPLATE_CALLERS` in
`tests/test_template_coupling_guard.py`:

```text
tests/test_result_handoff.py
tests/test_metric_results.py
```

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected before migration: failure with exactly those two offenders.

If other offenders appear, stop and report.

### 2. Migrate `tests/test_result_handoff.py`

Replace template fixture setup with:

```python
from tests.project_factory import create_approved_generic_project
```

The helper should become:

```python
def _prepare_real_run_project(tmp_path: Path):
    project_dir = create_approved_generic_project(
        tmp_path,
        created_at_utc="2026-06-01T00:00:00Z",
    )
    package = prepare_real_run(
        project_dir,
        created_at_utc="2026-06-01T00:20:00Z",
    )
    return project_dir, package
```

Remove imports and helpers that exist only for `create_project_from_template()`,
manual package build, manual approval, or `FN/WN/FP/WP` template overlay.

Preserve all `check_real_run()` behavior assertions.

### 3. Migrate `tests/test_metric_results.py`

Replace template fixture setup with:

```python
from tests.project_factory import create_approved_generic_project
```

Keep:

```python
from hermes_workflow.package import sha256_file
```

The ready-project helper should become:

```python
def _create_ready_project(tmp_path: Path) -> Path:
    project_dir = create_approved_generic_project(
        tmp_path,
        created_at_utc="2026-06-02T00:00:00Z",
    )
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir
```

Add helpers that derive metric names from
`runs/real/real_001/metric_extraction_request.json`.

Replace hardcoded expected issue strings containing `metric rise` with templates
formatted using the first requested metric name.

Replace hardcoded `"rise"` payload names in standalone model tests with
`"metric_gain"` unless the test is intentionally verifying arbitrary invalid shape.

Replace waveform-manifest incidental parameters:

```python
{"FN": "1e-6", "WN": "2e-6"}
```

with:

```python
{"VAR_INT": "1", "VAR_WIDTH": "0.2u"}
```

Do not weaken assertions. Preserve exact issue-message checks by deriving the
metric name, not by changing to broad substring checks.

### 4. Update inventory

Update:

```text
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Record Phase 2 completion:

- `tests/test_result_handoff.py` migrated.
- `tests/test_metric_results.py` migrated.
- Both removed from `ALLOWED_TEMPLATE_CALLERS`.
- Remaining deferred files are still deferred.

## Verification Commands

Run all commands and report exact results.

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_result_handoff.py -q
```

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_metric_results.py -q
```

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_project_factory.py tests/test_template_coupling_guard.py -q
```

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_result_handoff.py \
  tests/test_metric_results.py -q
```

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

```bash
git diff --check
```

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Also run these checks:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" tests/test_result_handoff.py tests/test_metric_results.py || true
```

```bash
grep -n '"rise"' tests/test_metric_results.py || true
```

Expected: no output from both grep checks.

## Final Report Format

Report:

1. Files modified.
2. Exact migration summary for each target file.
3. Guard allowlist before/after count.
4. Exact verification command results.
5. Confirmation that release checkout was untouched.
6. Confirmation that `graphify-out/` was untouched/still untracked.
7. Any remaining risks or deferred work.

Do not claim full cleanup is complete. Claim only Phase 2 completion if all
verification passes.
