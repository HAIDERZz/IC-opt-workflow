# Approval Gate Template Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `tests/test_approvals.py` from packaged-template setup to the generic project factory.

**Architecture:** Keep the migration local to the approval test file. Use `tests.project_factory` to create valid optimize and fix-run projects, add small local helpers for variable lookup and report writing, then remove the file from the template-coupling guard allowlist.

**Tech Stack:** Python 3.11, pytest, PyYAML, repo-local `tests/project_factory.py`, existing Hermes approval/package APIs.

---

## File Structure

- Modify `tests/test_approvals.py`
  - Replace direct `create_project_from_template()` setup with generic factory helpers.
  - Add local helpers for approved variable names and generic preflight reports.
  - Keep all approval/rejection assertions behaviorally equivalent.
- Modify `tests/test_template_coupling_guard.py`
  - Remove `tests/test_approvals.py` from `ALLOWED_TEMPLATE_CALLERS`.
- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Record Phase 6 status, verification, and remaining deferred work.

## Task 0: Baseline Audit

**Files:**
- Read: `tests/test_approvals.py`
- Read: `tests/project_factory.py`
- Read: `tests/report_helpers.py`
- Read: `src/hermes_workflow/approvals.py`
- Read: `tests/test_template_coupling_guard.py`

- [ ] **Step 1: Confirm clean starting state**

Run:

```bash
git status --short
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected:

- Dev checkout has only expected untracked working files such as `graphify-out/`
  or the Phase 6 planning files.
- Release checkout prints no modified files.

- [ ] **Step 2: Confirm current coupling and consumer scope**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" \
  tests/test_approvals.py || true
grep -R --exclude-dir=__pycache__ -n \
  "from tests.test_approvals\|tests.test_approvals" tests || true
```

Expected before migration:

- The first command shows old coupling inside `tests/test_approvals.py`.
- The second command shows no source-level external imports. Ignore binary
  `__pycache__` matches if they exist; do not edit cache files.

- [ ] **Step 3: Run current target tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_approvals.py -q
```

Expected:

- The existing approval tests pass before migration.

## Task 1: Replace Project Setup Imports and Add Local Helpers

**Files:**
- Modify: `tests/test_approvals.py`
- Test: `tests/test_approvals.py`

- [ ] **Step 1: Replace imports**

Remove this import:

```python
from hermes_workflow.package import build_execution_package, create_project_from_template
```

Add these imports:

```python
import yaml

from hermes_workflow.package import build_execution_package
from tests.project_factory import create_generic_project, create_packaged_generic_project
```

Keep:

```python
from hermes_workflow.approvals import decide_first_real_run, decide_fix_run_real_run
from tests.report_helpers import write_json, write_pass_reports
```

- [ ] **Step 2: Add a variable-name helper**

Add near the top of `tests/test_approvals.py`, after imports:

```python
def _variable_names(project_dir: Path) -> tuple[str, ...]:
    payload = yaml.safe_load(
        (project_dir / "config" / "variables.yaml").read_text(encoding="utf-8")
    )
    return tuple(variable["name"] for variable in payload["variables"])
```

- [ ] **Step 3: Add optimize project helpers**

Add:

```python
def _create_project(tmp_path: Path, *, name: str = "approval_project") -> Path:
    return create_generic_project(tmp_path, name=name)


def _create_packaged_project(
    tmp_path: Path,
    *,
    name: str = "approval_project",
    created_at_utc: str = "2026-05-28T00:00:00Z",
) -> Path:
    return create_packaged_generic_project(
        tmp_path,
        name=name,
        created_at_utc=created_at_utc,
    )


def _write_pass_reports(project_dir: Path) -> None:
    write_pass_reports(project_dir, variable_names=_variable_names(project_dir))
```

- [ ] **Step 4: Add a generic netlist pass report helper for partial-report tests**

Add:

```python
def _write_netlist_pass_report(project_dir: Path) -> None:
    approved_variables = {name: True for name in _variable_names(project_dir)}
    write_json(
        project_dir / "reports" / "netlist_preparation_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "exported_input_scs": "netlists/exported/input.scs",
            "template_scs": "netlists/templates/template.scs",
            "approved_variables_template_status": approved_variables,
            "analysis_statements": ["tran", "dc"],
            "forbidden_setup_changes_detected": False,
            "issues": [],
        },
    )
```

- [ ] **Step 5: Add a generic dry-run pass report helper for partial-report tests**

Add:

```python
def _write_dry_run_pass_report(project_dir: Path) -> None:
    write_json(
        project_dir / "reports" / "dry_run_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "rendered_candidate_scs": "runs/dry_run/input.scs",
            "placeholder_check": {
                "unresolved_placeholders": [],
                "unexpected_template_variables": [],
            },
            "metrics_import_ok": True,
            "mock_metrics_ok": True,
            "objective_ok": True,
            "constraints_ok": True,
            "ledger_write_ok": True,
            "state_write_ok": True,
            "issues": [],
        },
    )
```

- [ ] **Step 6: Add a fix-run packaged project helper**

Add:

```python
def _create_packaged_fix_run_project(
    tmp_path: Path,
    *,
    name: str = "fix_run_approval_project",
    created_at_utc: str = "2026-06-16T00:00:00Z",
) -> Path:
    return create_packaged_generic_project(
        tmp_path,
        name=name,
        workflow_mode="fix_run",
        created_at_utc=created_at_utc,
    )
```

Do not hand-write `config/workflow.yaml` or `config/fixed_points.yaml` in the
tests. The generic factory already writes a valid fix-run workflow with generated
variable names.

## Task 2: Migrate Optimizer Approval Tests

**Files:**
- Modify: `tests/test_approvals.py`
- Test: `tests/test_approvals.py`

- [ ] **Step 1: Migrate the approval happy path**

Change `test_approval_gate_writes_approve_instruction` setup to:

```python
project_dir = _create_packaged_project(tmp_path)
_write_pass_reports(project_dir)
```

Keep the existing decision, reason, allowed action, and
`approved_config_hashes["config/project_config.yaml"]` assertions.

- [ ] **Step 2: Migrate dry-run failure rejection**

Change `test_approval_gate_writes_reject_instruction_when_preflight_fails` setup
to:

```python
project_dir = _create_packaged_project(tmp_path)
_write_pass_reports(project_dir)
```

Keep the mutation:

```python
dry_run_payload["status"] = "fail"
dry_run_payload["issues"] = ["mock metric failed"]
```

Keep the exact reason assertions:

```python
assert "dry run status is fail" in instruction["reason"]
assert "mock metric failed" in instruction["reason"]
```

- [ ] **Step 3: Migrate missing execution manifest rejection**

Change `test_approval_gate_rejects_missing_execution_manifest` setup to:

```python
project_dir = _create_project(tmp_path)
```

Keep the assertions that the decision rejects, the reason is
`"execution manifest is missing"`, approved hashes are `{}`, and the written
instruction equals the returned instruction.

- [ ] **Step 4: Migrate invalid project config rejection**

Change `test_approval_gate_rejects_invalid_project_config` setup to:

```python
project_dir = _create_packaged_project(tmp_path)
_write_pass_reports(project_dir)
(project_dir / "config" / "variables.yaml").unlink()
```

Keep the assertions that the reason mentions `config/variables.yaml` and
`required config file is missing`, and that
`approved_config_hashes["config/project_config.yaml"]` is present.

- [ ] **Step 5: Migrate invalid execution manifest rejection**

Change `test_approval_gate_rejects_invalid_execution_manifest` setup to:

```python
project_dir = _create_packaged_project(tmp_path)
_write_pass_reports(project_dir)
manifest_path = project_dir / "execution_package" / "execution_manifest.json"
manifest_path.write_text("{not-json", encoding="utf-8")
```

Keep the assertions that the reason contains `execution manifest is invalid` and
approved hashes are `{}`.

- [ ] **Step 6: Migrate manifest missing config hashes rejection**

Change `test_approval_gate_rejects_manifest_missing_config_hashes` setup to:

```python
project_dir = _create_packaged_project(tmp_path)
_write_pass_reports(project_dir)
manifest_path = project_dir / "execution_package" / "execution_manifest.json"
manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
del manifest_payload["immutable_config_files"]
write_json(manifest_path, manifest_payload)
```

Keep the existing rejection reason and empty-hashes assertions.

- [ ] **Step 7: Migrate health report started rejection**

Change `test_approval_gate_rejects_health_report_with_real_run_started` setup to:

```python
project_dir = _create_packaged_project(tmp_path)
_write_pass_reports(project_dir)
```

Keep the ledger write, health report mutation, and all reason assertions.

- [ ] **Step 8: Migrate missing preflight report rejection**

Change `test_approval_gate_rejects_missing_preflight_reports` setup to:

```python
project_dir = _create_packaged_project(tmp_path)
_write_dry_run_pass_report(project_dir)
```

Do not write the netlist report or health check. Keep assertions that the reason
mentions:

```python
"required preflight reports missing:"
"reports/netlist_preparation_report.json"
"state/health_check.json"
```

and does not mention:

```python
"reports/dry_run_report.json"
```

- [ ] **Step 9: Migrate missing health check rejection**

Change `test_approval_gate_rejects_missing_health_check` setup to:

```python
project_dir = _create_packaged_project(tmp_path)
_write_netlist_pass_report(project_dir)
_write_dry_run_pass_report(project_dir)
```

Do not write `state/health_check.json`. Keep assertions that the reason mentions
`state/health_check.json` and does not mention
`reports/netlist_preparation_report.json`.

- [ ] **Step 10: Migrate malformed present report strict-loading test**

Change `test_approval_gate_preserves_strict_loading_for_malformed_present_report`
setup to:

```python
project_dir = _create_packaged_project(tmp_path)
(project_dir / "reports").mkdir(parents=True, exist_ok=True)
(project_dir / "reports" / "netlist_preparation_report.json").write_text(
    "not-valid-json",
    encoding="utf-8",
)
(project_dir / "reports" / "dry_run_report.json").write_text("{}", encoding="utf-8")
(project_dir / "state").mkdir(parents=True, exist_ok=True)
(project_dir / "state" / "health_check.json").write_text("{}", encoding="utf-8")
```

Keep:

```python
with pytest.raises((json.JSONDecodeError, ValueError)):
    decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )
```

- [ ] **Step 11: Keep missing-project-dir test unchanged**

`test_approval_gate_handles_missing_project_dir_for_instruction` does not use the
template API. Keep the project path as:

```python
project_dir = tmp_path / "nonexistent"
```

- [ ] **Step 12: Migrate optimizer preflight regression**

Change `test_optimizer_approval_still_requires_preflight_reports` setup to:

```python
project_dir = _create_packaged_project(
    tmp_path,
    name="optimizer_preflight_regression",
    created_at_utc="2026-06-16T00:00:00Z",
)
```

Do not call `_write_pass_reports(project_dir)`. Keep all required-preflight reason
assertions.

- [ ] **Step 13: Run optimizer approval subset**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_approvals.py -q
```

Expected:

- `tests/test_approvals.py` passes, or any failure is a direct migration issue in
  this file.

## Task 3: Migrate Fix-Run Approval Tests

**Files:**
- Modify: `tests/test_approvals.py`
- Test: `tests/test_approvals.py`

- [ ] **Step 1: Migrate fix-run no-preflight approval**

Change `test_fix_run_approval_does_not_require_optimizer_preflight_reports`
setup to:

```python
project_dir = _create_packaged_fix_run_project(
    tmp_path,
    name="fix_run_approval_project",
)
```

Remove all manual writes to `config/workflow.yaml` and `config/fixed_points.yaml`.
Keep assertions:

```python
assert instruction["decision"] == "approve_first_real_run"
assert instruction["reason"] == "fix-run config validation passed"
assert "prepare_fixed_candidate_real_run" in instruction["allowed_actions"]
assert "run_standalone_spectre_optimizer" in instruction["forbidden_actions"]
assert not (project_dir / "reports" / "dry_run_report.json").exists()
```

- [ ] **Step 2: Migrate fix-run distinct-actions approval**

Change `test_fix_run_approval_uses_distinct_allowed_actions` setup to:

```python
project_dir = _create_packaged_fix_run_project(
    tmp_path,
    name="fix_run_distinct_actions",
)
```

Remove all manual writes to `config/workflow.yaml` and `config/fixed_points.yaml`.
Keep assertions:

```python
assert instruction["decision"] == "approve_first_real_run"
assert "prepare_fixed_candidate_real_run" in instruction["allowed_actions"]
assert "run_standalone_spectre_optimizer" not in instruction["allowed_actions"]
assert "run_standalone_spectre_optimizer" in instruction["forbidden_actions"]
```

- [ ] **Step 3: Run target tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_approvals.py -q
```

Expected:

- All approval tests pass.

## Task 4: Shrink Guard and Update Inventory

**Files:**
- Modify: `tests/test_template_coupling_guard.py`
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Remove approvals from allowlist**

Remove this line from `ALLOWED_TEMPLATE_CALLERS`:

```python
"tests/test_approvals.py",
```

Expected allowlist count after this change: 15.

- [ ] **Step 2: Update inventory phase list and summary**

In
`docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`,
update the opening `Phases:` line to include Phase 6:

```markdown
Phases: 1 (factory + guard + first wave), 2 (real-run handoff + metric-result contracts),
3 (first real-run package + recovery), 4 (next-run cluster), 5 (netlist + dry-run preflight),
and 6 (approval gate)
```

Update the introductory paragraph to say Phase 6 migrated the approval gate tests.

- [ ] **Step 3: Add Phase 6 status section**

Insert a new section above `## Phase 5 status`:

```markdown
## Phase 6 status

Migrated `tests/test_approvals.py` away from direct
`create_project_from_template()` usage. Optimizer approval tests now use generic
factory projects and report helpers that derive approved variable names from
`config/variables.yaml`; fix-run approval tests now use the generic factory's
`workflow_mode="fix_run"` project instead of hand-written old fixed-point
variables.

Coverage preserved:

- optimizer approval after manifest, validation, and preflight pass,
- optimizer rejection for dry-run failure, missing/malformed manifest, invalid
  project config, missing manifest hashes, health issues, missing preflight
  reports, malformed present reports, and missing project directory,
- fix-run approval without optimizer preflight reports,
- distinct fix-run allowed/forbidden actions.

`tests/test_approvals.py` was removed from `ALLOWED_TEMPLATE_CALLERS`
(allowlist 16 -> 15). No external tests import from `tests.test_approvals`.
```

- [ ] **Step 4: Move approvals out of remaining waves**

Remove `tests/test_approvals.py` from:

```markdown
### Approvals and packaging
```

Keep the rest of that group unchanged.

- [ ] **Step 5: Add Phase 6 verification section**

After the verification commands have actually been run, add a Phase 6 subsection
under `## Verification`. The section must list each command and its observed
result. Do not add pending verification bullets before running the commands.

```markdown
### Phase 6

- `pytest tests/test_approvals.py -q` -> `14 passed`
- `pytest tests/test_template_coupling_guard.py -q` -> `1 passed`
- `pytest tests/test_project_factory.py tests/test_template_coupling_guard.py tests/test_health.py tests/test_optimizer_flow.py tests/test_result_handoff.py tests/test_metric_results.py tests/test_real_run.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_candidate_injection_real_run.py tests/test_optimizer_suggestion.py tests/test_optimizer_loop.py tests/test_netlists.py tests/test_dry_run.py tests/test_approvals.py -q` -> `280 passed`
- `pytest -q` -> `1193 passed`
- `ruff check src tests` -> `All checks passed!`
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean (release checkout untouched)
- grep `create_project_from_template|bridge_test_inv|FN|WN|FP|WP` over `tests/test_approvals.py` -> no matches
- grep `from tests.test_approvals|tests.test_approvals` over `tests/` -> no source-level matches
- `ALLOWED_TEMPLATE_CALLERS` count: 16 -> 15.
```

The numeric examples above are the expected shape based on the current suite
counts. If the real counts differ, write the real observed counts and explain why.

- [ ] **Step 6: Run guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

- `1 passed`

## Task 5: Verification

**Files:**
- Verify: target test, guard, regression group, full suite

- [ ] **Step 1: Run target and guard together**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/test_approvals.py \
  tests/test_template_coupling_guard.py \
  -q
```

Expected:

- Both files pass together.

- [ ] **Step 2: Run drift checks**

Run:

```bash
grep -n "create_project_from_template\|bridge_test_inv\|FN\|WN\|FP\|WP" \
  tests/test_approvals.py || true
grep -R --exclude-dir=__pycache__ -n \
  "from tests.test_approvals\|tests.test_approvals" tests || true
```

Expected:

- No matches in `tests/test_approvals.py`.
- No source-level cross-test imports. Ignore binary `__pycache__` matches if they
  exist; do not edit cache files.

- [ ] **Step 3: Run Phase 1-6 regression group**

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
- any other test file must be modified to make `tests/test_approvals.py` pass,
- `tests.test_approvals` has a source-level external consumer not found in the
  baseline audit,
- the generic factory must learn behavior that is specific to approval tests only,
- remote, adapter, backend, retention, or fix-run flow tests become involved,
- full-suite failures reveal a separate existing product bug.
