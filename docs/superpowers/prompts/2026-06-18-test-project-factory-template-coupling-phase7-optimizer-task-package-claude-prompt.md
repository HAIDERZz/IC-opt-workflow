# Claude Prompt: Phase 7 Optimizer Task Package Template Decoupling

You are working in:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`

Do not touch the release checkout:

`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`

Do not edit or stage `graphify-out/`.
Do not commit, tag, push, or publish.

## Goal

Implement Phase 7 of the Test Project Factory and Template Coupling Cleanup:
migrate the optimizer task package tests away from the packaged release template.

This phase covers exactly:

- `tests/test_optimizer_task_package.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

## Read First

Read these files before editing:

- `docs/superpowers/specs/2026-06-18-test-project-factory-template-coupling-phase7-optimizer-task-package-spec.md`
- `docs/superpowers/plans/2026-06-18-test-project-factory-template-coupling-phase7-optimizer-task-package-plan.md`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
- `tests/project_factory.py`
- `tests/test_template_coupling_guard.py`
- `tests/test_optimizer_task_package.py`
- `src/hermes_workflow/optimizer_task_package.py`
- `src/hermes_workflow/cli.py`

If codegraph is available, use it to inspect:

- `tests/test_optimizer_task_package.py`
- `build_optimizer_execution_task_package`
- `create_generic_project`
- the `package-optimizer-task` CLI entrypoint

If graphify is available and `graphify-out/` exists, use it only for orientation.
Source files and tests are authoritative.

## Strict Scope

You may modify:

- `tests/test_optimizer_task_package.py`
- `tests/test_template_coupling_guard.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Prefer local helper functions inside `tests/test_optimizer_task_package.py`.

If any other file appears necessary, stop and report options before editing it.
Do not modify production source in this phase.
Do not modify packaged templates or examples.
Do not modify the Phase 7 spec, plan, or this prompt.

## Required Behavior

1. Remove direct `create_project_from_template()` usage from
   `tests/test_optimizer_task_package.py`.
2. Use `tests/project_factory.py` as the project source of truth.
3. Preserve optimizer task package coverage:
   - native TuRBO task and manifest writing,
   - OpenBox task and manifest writing,
   - config-driven `turbo_trust_region` backend routing,
   - config-driven `openbox_prf_eic` strategy routing,
   - OpenBox continuation package,
   - CLI package generation for native and OpenBox,
   - shell-safe absolute command paths,
   - scheduler settings not mislabeled as Spectre/OCEAN settings,
   - forbidden actions kept out of required behavior,
   - OpenBox fallback rule kept in required behavior,
   - explicit OpenBox strategy included in task and manifest.
4. Preserve package numeric behavior by creating generic projects with:
   - `max_evaluations=100`,
   - `batch_size=10`,
   - `parallel_jobs=10`.
5. Derive config-sensitive assertions from generated `config/optimizer.yaml` and
   `config/spectre.yaml` when practical.
6. Replace optimizer YAML text replacement with structured YAML mutation.
7. Remove old release-template strings from the target file:
   - `create_project_from_template`
   - `bridge_test_inv`
   - `FN`
   - `WN`
   - `FP`
   - `WP`
8. Remove `tests/test_optimizer_task_package.py` from `ALLOWED_TEMPLATE_CALLERS`;
   allowlist count should shrink from 15 to 14.
9. Update the inventory report with Phase 7 status and exact verification results.

## Implementation Guidance

Add local helpers in `tests/test_optimizer_task_package.py`:

- constants:
  - `PROJECT_NAME = "optimizer_task_project"`
  - `MAX_EVALUATIONS = 100`
  - `BATCH_SIZE = 10`
  - `PARALLEL_JOBS = 10`
  - `CADENCE_CSHRC = Path("/opt/ic-opt/cadence_env.csh")`
- `_create_optimizer_project(...)` using `create_generic_project(...)`
- `_read_yaml(path)`
- `_write_yaml(path, payload)`
- `_set_optimizer_settings(project_dir, algorithm=..., strategy=...)`
- `_optimizer_settings(project_dir)`
- `_spectre_settings(project_dir)`

Use `str(project_dir.resolve())` and `str(CADENCE_CSHRC.resolve())` in direct API
command assertions, because `build_optimizer_execution_task_package()` resolves
both paths.

For the relative path shell-safety test, keep the relative project path behavior:

```python
monkeypatch.chdir(tmp_path)
project_dir = Path(PROJECT_NAME)
create_generic_project(
    Path("."),
    name=PROJECT_NAME,
    max_evaluations=MAX_EVALUATIONS,
    batch_size=BATCH_SIZE,
    parallel_jobs=PARALLEL_JOBS,
)
```

Then keep assertions that manifest paths and command entries are resolved
absolute paths.

## Verification Commands

Run the baseline target test before editing:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_task_package.py -q
```

Run focused checks after migration:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_task_package.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_optimizer_task_package.py \
  tests/test_template_coupling_guard.py \
  -q
```

Run the Phase 1-7 regression group:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_project_factory.py \
  tests/test_template_coupling_guard.py \
  tests/test_health.py \
  tests/test_optimizer_flow.py \
  tests/test_result_handoff.py \
  tests/test_metric_results.py \
  tests/test_real_run.py \
  tests/test_real_run_recovery.py \
  tests/test_next_real_run.py \
  tests/test_candidate_injection_real_run.py \
  tests/test_optimizer_suggestion.py \
  tests/test_optimizer_loop.py \
  tests/test_netlists.py \
  tests/test_dry_run.py \
  tests/test_approvals.py \
  tests/test_optimizer_task_package.py \
  -q
```

Run final checks:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Run drift checks:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" \
  tests/test_optimizer_task_package.py || true
grep -R --exclude-dir=__pycache__ -n \
  "from tests.test_optimizer_task_package\|tests.test_optimizer_task_package" tests || true
```

Expected:

- No old-template matches in `tests/test_optimizer_task_package.py`.
- No source-level cross-test imports from `tests.test_optimizer_task_package`.
- Guard passes with allowlist count 14.
- Release checkout remains clean.

## Stop Conditions

Stop and report before broadening scope if:

- a production source change appears necessary,
- any other test file must be modified to make `tests/test_optimizer_task_package.py` pass,
- `tests.test_optimizer_task_package` has a source-level external consumer not
  found in the baseline audit,
- the generic factory must learn behavior that is specific to optimizer task
  package tests only,
- run-retention, progress-state, fix-run flow, remote, adapter, or backend tests
  become involved,
- full-suite failures reveal a separate existing product bug.

## Final Report Required

Report:

- files modified,
- optimizer task package migration summary,
- helper functions added inside `tests/test_optimizer_task_package.py`,
- direct API package coverage preserved,
- CLI package coverage preserved,
- command/path safety coverage preserved,
- guard allowlist count before and after,
- exact verification command results,
- drift grep results,
- release checkout status,
- confirmation that `graphify-out/` was untouched,
- any deferred work.

Do not claim the broader template-coupling cleanup is complete. Claim only Phase
7 if all acceptance criteria pass.
