# Optimizer Task Package Template Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `tests/test_optimizer_task_package.py` from packaged-template setup to the generic project factory.

**Architecture:** Keep this phase local to the optimizer task package tests. Add local helpers that create generic projects with the same optimizer scheduler settings the old template provided, mutate optimizer config through YAML, and derive assertion values from config where useful.

**Tech Stack:** Python 3.11, pytest, PyYAML, Typer `CliRunner`, repo-local `tests/project_factory.py`, existing Hermes optimizer task package APIs.

---

## File Structure

- Modify `tests/test_optimizer_task_package.py`
  - Replace direct `create_project_from_template()` setup with generic factory helpers.
  - Add local helpers for config-driven project creation and optimizer YAML mutation.
  - Preserve all task text, manifest, CLI, command, and section-placement assertions.
- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_optimizer_task_package.py` from `ALLOWED_TEMPLATE_CALLERS`.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Record Phase 7 status, verification, and remaining deferred work.

## Task 0: Baseline Audit

**Files:**
- Read: `tests/test_optimizer_task_package.py`
- Read: `tests/project_factory.py`
- Read: `src/hermes_workflow/optimizer_task_package.py`
- Read: `src/hermes_workflow/cli.py`
- Read: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Confirm clean starting state**

Run:

```bash
git status --short
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected:

- Dev checkout has only expected untracked working files such as `graphify-out/`
  or the Phase 7 planning files.
- Release checkout prints no modified files.

- [ ] **Step 2: Confirm current coupling and consumer scope**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" \
  tests/test_optimizer_task_package.py || true
grep -R --exclude-dir=__pycache__ -n \
  "from tests.test_optimizer_task_package\|tests.test_optimizer_task_package" tests || true
```

Expected before migration:

- The first command shows old coupling inside `tests/test_optimizer_task_package.py`.
- The second command shows no source-level external imports.

- [ ] **Step 3: Run current target tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_task_package.py -q
```

Expected:

- The existing optimizer task package tests pass before migration.

## Task 1: Replace Imports and Add Local Helpers

**Files:**
- Modify: `tests/test_optimizer_task_package.py`
- Test: `tests/test_optimizer_task_package.py`

- [ ] **Step 1: Replace imports**

Remove:

```python
from hermes_workflow.package import create_project_from_template
```

Add:

```python
import yaml

from tests.project_factory import create_generic_project
```

Keep existing imports for `json`, `Path`, `CliRunner`, `app`, and
`build_optimizer_execution_task_package`.

- [ ] **Step 2: Add local constants**

Add near the top of the file after `runner = CliRunner()`:

```python
PROJECT_NAME = "optimizer_task_project"
MAX_EVALUATIONS = 100
BATCH_SIZE = 10
PARALLEL_JOBS = 10
CADENCE_CSHRC = Path("/opt/ic-opt/cadence_env.csh")
```

- [ ] **Step 3: Add a generic project helper**

Add:

```python
def _create_optimizer_project(
    tmp_path: Path,
    *,
    name: str = PROJECT_NAME,
    max_evaluations: int = MAX_EVALUATIONS,
    batch_size: int = BATCH_SIZE,
    parallel_jobs: int = PARALLEL_JOBS,
) -> Path:
    return create_generic_project(
        tmp_path,
        name=name,
        max_evaluations=max_evaluations,
        batch_size=batch_size,
        parallel_jobs=parallel_jobs,
    )
```

This preserves the old template's optimizer package numbers without depending on
the old template tree.

- [ ] **Step 4: Add structured YAML helpers**

Add:

```python
def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _set_optimizer_settings(
    project_dir: Path,
    *,
    algorithm: str | None = None,
    strategy: str | None = None,
) -> None:
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = _read_yaml(optimizer_path)
    settings = payload["optimizer"]
    if algorithm is not None:
        settings["algorithm"] = algorithm
    if strategy is not None:
        settings["strategy"] = strategy
    _write_yaml(optimizer_path, payload)
```

- [ ] **Step 5: Add config-derived assertion helpers**

Add:

```python
def _optimizer_settings(project_dir: Path) -> dict:
    return _read_yaml(project_dir / "config" / "optimizer.yaml")["optimizer"]


def _spectre_settings(project_dir: Path) -> dict:
    return _read_yaml(project_dir / "config" / "spectre.yaml")["spectre"]
```

Use these helpers when asserting `max_evals`, `batch_size`, `parallel_jobs`, and
`threads_per_run`.

## Task 2: Migrate Direct API Package Tests

**Files:**
- Modify: `tests/test_optimizer_task_package.py`
- Test: `tests/test_optimizer_task_package.py`

- [ ] **Step 1: Migrate scheduler/Spectre split test**

Change setup in
`test_optimizer_task_package_does_not_label_parallel_jobs_as_spectre_setting` to:

```python
project_dir = _create_optimizer_project(tmp_path)
optimizer = _optimizer_settings(project_dir)
spectre = _spectre_settings(project_dir)
```

Keep the existing `build_optimizer_execution_task_package(...)` call, using
`cadence_cshrc=CADENCE_CSHRC`.

Assert scheduler values from config:

```python
assert "parallel_jobs" not in manifest_payload["spectre_settings"]
assert manifest_payload["scheduler"]["candidate_parallelism"] == spectre["parallel_jobs"]
assert manifest_payload["scheduler"]["batch_size"] == optimizer["batch_size"]
assert manifest_payload["scheduler"]["inside_candidate_execution"] == "serial"
assert manifest_payload["parallel_jobs"] == spectre["parallel_jobs"]
assert manifest_payload["batch_size"] == optimizer["batch_size"]
```

Keep the audit-section assertion that `parallel_jobs` is absent from the
`## Spectre/OCEAN Settings Audit` slice.

- [ ] **Step 2: Migrate native task/manifest test**

Change setup in
`test_build_optimizer_execution_task_package_writes_task_and_manifest` to:

```python
project_dir = _create_optimizer_project(tmp_path)
optimizer = _optimizer_settings(project_dir)
spectre = _spectre_settings(project_dir)
```

Keep existing task path, manifest path, task text, required artifact, command, and
audit command assertions. Replace numeric assertions with:

```python
assert manifest_payload["max_evals"] == optimizer["max_evaluations"]
assert manifest_payload["spectre_settings"]["threads_per_run"] == spectre["threads_per_run"]
assert manifest_payload["scheduler"]["candidate_parallelism"] == spectre["parallel_jobs"]
```

The expected command should still use `str(project_dir.resolve())` because
`build_optimizer_execution_task_package()` resolves the project path:

```python
assert manifest_payload["command"] == [
    "hermes-workflow",
    "run-native-turbo",
    str(project_dir.resolve()),
    "--parallel",
    "--cadence-cshrc",
    str(CADENCE_CSHRC.resolve()),
]
```

- [ ] **Step 3: Migrate OpenBox task/manifest test**

Change setup in `test_build_optimizer_execution_task_package_writes_openbox_backend`
to:

```python
project_dir = _create_optimizer_project(tmp_path)
optimizer = _optimizer_settings(project_dir)
spectre = _spectre_settings(project_dir)
```

Keep the OpenBox task text and required artifact assertions. Replace numeric
assertions with config-derived values:

```python
assert manifest_payload["batch_size"] == optimizer["batch_size"]
assert manifest_payload["parallel_jobs"] == spectre["parallel_jobs"]
assert manifest_payload["scheduler"]["candidate_parallelism"] == spectre["parallel_jobs"]
```

Command assertions should use `str(project_dir.resolve())` and
`str(CADENCE_CSHRC.resolve())`.

- [ ] **Step 4: Migrate OpenBox continuation test**

Change setup in `test_build_optimizer_execution_task_package_writes_openbox_continuation`
to:

```python
project_dir = _create_optimizer_project(tmp_path)
optimizer = _optimizer_settings(project_dir)
```

Keep continuation task text assertions and replace:

```python
assert manifest_payload["max_evals"] == optimizer["max_evaluations"]
```

Command and audit command assertions should use `str(project_dir.resolve())` and
`str(CADENCE_CSHRC.resolve())`.

## Task 3: Migrate Config Strategy Routing Tests

**Files:**
- Modify: `tests/test_optimizer_task_package.py`
- Test: `tests/test_optimizer_task_package.py`

- [ ] **Step 1: Replace turbo strategy text replacement**

In `test_build_optimizer_execution_task_package_uses_config_turbo_strategy_backend`,
replace setup with:

```python
project_dir = _create_optimizer_project(tmp_path)
_set_optimizer_settings(project_dir, algorithm="turbo", strategy="turbo_trust_region")
```

Remove all `optimizer_path.read_text(...).replace(...)` code.

Keep assertions that backend becomes `native_turbo`, strategy becomes
`turbo_trust_region`, and the command starts with:

```python
[
    "hermes-workflow",
    "run-native-turbo",
    str(project_dir.resolve()),
]
```

- [ ] **Step 2: Replace OpenBox strategy text replacement**

In `test_build_optimizer_execution_task_package_uses_config_openbox_strategy`,
replace setup with:

```python
project_dir = _create_optimizer_project(tmp_path)
_set_optimizer_settings(project_dir, algorithm="openbox", strategy="openbox_prf_eic")
```

Remove all `optimizer_path.read_text(...).replace(...)` code.

Keep assertions that backend becomes `openbox`, strategy becomes
`openbox_prf_eic`, and the manifest command includes:

```python
["--strategy", "openbox_prf_eic"]
```

## Task 4: Migrate CLI and Command-Safety Tests

**Files:**
- Modify: `tests/test_optimizer_task_package.py`
- Test: `tests/test_optimizer_task_package.py`

- [ ] **Step 1: Migrate native CLI package test**

Change setup in `test_package_optimizer_task_cli_writes_task_and_manifest` to:

```python
project_dir = _create_optimizer_project(tmp_path)
```

Keep the `runner.invoke(...)` command. Fix any indentation around `"--parallel"` if
needed while preserving behavior. Keep stdout and artifact-existence assertions.

- [ ] **Step 2: Migrate OpenBox CLI package test**

Change setup in `test_package_optimizer_task_cli_writes_openbox_manifest` to:

```python
project_dir = _create_optimizer_project(tmp_path)
```

Keep backend, strategy, command, and manifest assertions.

- [ ] **Step 3: Migrate OpenBox continuation CLI package test**

Change setup in
`test_package_optimizer_task_cli_writes_openbox_continuation_manifest` to:

```python
project_dir = _create_optimizer_project(tmp_path)
```

Keep continuation, `additional_evals`, and command assertions.

- [ ] **Step 4: Migrate absolute shell-safe command test**

In `test_optimizer_task_package_uses_absolute_shell_safe_command`, keep the
relative path behavior by changing setup to:

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
cadence_cshrc = tmp_path / "cadence env.csh"
```

Keep assertions that manifest paths and command entries are resolved absolute
paths and that the quoted cadence path appears in task text.

## Task 5: Migrate Task Text Section Tests

**Files:**
- Modify: `tests/test_optimizer_task_package.py`
- Test: `tests/test_optimizer_task_package.py`

- [ ] **Step 1: Migrate forbidden-action section test**

Change setup in
`test_optimizer_execution_task_keeps_forbidden_actions_in_forbidden_section` to:

```python
project_dir = _create_optimizer_project(tmp_path)
```

Keep all section-splitting and text assertions unchanged.

- [ ] **Step 2: Migrate OpenBox fallback required-behavior test**

Change setup in
`test_optimizer_execution_task_keeps_openbox_fallback_in_required_behavior` to:

```python
project_dir = _create_optimizer_project(tmp_path)
```

Keep all required-behavior assertions unchanged.

- [ ] **Step 3: Migrate explicit OpenBox strategy task test**

Change setup in `test_build_openbox_task_package_includes_optimizer_strategy` to:

```python
project_dir = _create_optimizer_project(tmp_path)
```

Keep strategy task text, manifest strategy, command, and required artifact
assertions. Use `str(project_dir.resolve())` for command prefix.

- [ ] **Step 4: Run target tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_optimizer_task_package.py -q
```

Expected:

- All optimizer task package tests pass.

## Task 6: Shrink Guard and Update Inventory

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Remove optimizer task package from allowlist**

Remove this line from `ALLOWED_TEMPLATE_CALLERS`:

```python
"tests/test_optimizer_task_package.py",
```

Expected allowlist count after this change: 14.

- [ ] **Step 2: Update inventory phase list and summary**

In
`docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`,
update the opening `Phases:` line to include Phase 7:

```markdown
Phases: 1 (factory + guard + first wave), 2 (real-run handoff + metric-result contracts),
3 (first real-run package + recovery), 4 (next-run cluster), 5 (netlist + dry-run preflight),
6 (approval gate), and 7 (optimizer task package)
```

Update the introductory paragraph to say Phase 7 migrated the optimizer task
package tests.

- [ ] **Step 3: Add Phase 7 status section**

Insert a new section above `## Phase 6 status`:

```markdown
## Phase 7 status

Migrated `tests/test_optimizer_task_package.py` away from direct
`create_project_from_template()` usage. The file now creates generic projects
through `tests/project_factory.py` with explicit optimizer package settings
(`max_evaluations=100`, `batch_size=10`, `parallel_jobs=10`) so package behavior
remains comparable to the previous template-backed tests without depending on
the packaged example circuit. Strategy-routing tests mutate `config/optimizer.yaml`
through structured YAML instead of old template text replacement.

Coverage preserved: native TuRBO package generation, OpenBox package generation,
config-driven strategy routing, OpenBox continuation, CLI package entrypoints,
shell-safe absolute command paths, scheduler/Spectre settings separation,
forbidden-action section placement, OpenBox fallback guidance, and explicit
OpenBox strategy handling.

`tests/test_optimizer_task_package.py` was removed from
`ALLOWED_TEMPLATE_CALLERS` (allowlist 15 -> 14). No external tests import from
`tests.test_optimizer_task_package`.
```

- [ ] **Step 4: Move file out of remaining waves**

Remove `tests/test_optimizer_task_package.py` from:

```markdown
### Approvals and packaging
```

Keep the rest of that group unchanged.

- [ ] **Step 5: Add Phase 7 verification section after commands are run**

After the verification commands have actually been run, add a Phase 7 subsection
under `## Verification`. The section must list each command and its real command
result. The counts below are the expected shape from the current suite; if the
actual counts differ, write the actual counts and explain why.

```markdown
### Phase 7

- `pytest tests/test_optimizer_task_package.py -q` -> `13 passed`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_optimizer_task_package.py tests/test_template_coupling_guard.py -q` -> `14 passed`
- `pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py tests/test_optimizer_task_package.py -q` -> `294 passed`
- `pytest -q` -> `1194 passed`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep `create_project_from_template|bridge_test_inv|FN|WN|FP|WP` over `tests/test_optimizer_task_package.py` -> no matches
- grep `from tests.test_optimizer_task_package|tests.test_optimizer_task_package` over `tests/` -> no source-level matches
- `ALLOWED_TEMPLATE_CALLERS` count: 15 -> 14.
```

Do not write this verification section before running the commands.

## Task 7: Verification

**Files:**
- Verify: target test, guard, regression group, full suite

- [ ] **Step 1: Run target and guard together**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_optimizer_task_package.py \
  tests/test_template_coupling_guard.py \
  -q
```

Expected:

- Both files pass together.

- [ ] **Step 2: Run drift checks**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" \
  tests/test_optimizer_task_package.py || true
grep -R --exclude-dir=__pycache__ -n \
  "from tests.test_optimizer_task_package\|tests.test_optimizer_task_package" tests || true
```

Expected:

- No matches in `tests/test_optimizer_task_package.py`.
- No source-level cross-test imports.

- [ ] **Step 3: Run Phase 1-7 regression group**

Run:

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

Expected:

- Regression group passes.

- [ ] **Step 4: Run final checks**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected:

- Full suite passes.
- Ruff passes.
- Diff check is clean.
- Release checkout prints no modified files.

## Stop Conditions

Stop and report instead of broadening scope if:

- a production source change appears necessary,
- any other test file must be modified to make `tests/test_optimizer_task_package.py` pass,
- `tests.test_optimizer_task_package` has a source-level external consumer not
  found in the baseline audit,
- the generic factory must learn behavior that is specific to optimizer task
  package tests only,
- run-retention, progress-state, fix-run flow, remote, adapter, or backend tests
  become involved,
- full-suite failures reveal a separate existing product bug.
