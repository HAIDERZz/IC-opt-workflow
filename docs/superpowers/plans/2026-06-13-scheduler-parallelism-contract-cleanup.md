# B-02 Scheduler Parallelism Contract Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Do not use subagents unless the user explicitly asks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove fake `spectre.parallel_jobs` runtime metadata while preserving `parallel_jobs` as the real candidate-level scheduler concurrency setting.

**Architecture:** Keep the existing requirement/config input for compatibility, but stop copying `parallel_jobs` into per-child Spectre runtime contracts. OpenBox/TuRBO continue to read the config value for candidate batch concurrency. Adapters validate only fields they actually consume for a child run.

**Tech Stack:** Python 3.11, Pydantic schemas, Typer CLI, pytest, local/remote Spectre/OCEAN adapters, OpenBox backend, native TuRBO backend.

## Guardrails

- Develop only in `ic-auto-opt-workflow`.
- Do not sync `ic-auto-opt-workflow-v0.1` until dev tests and real-flow validation pass.
- Do not add CLI workload/resource flags.
- Do not change candidate/testbench/corner execution semantics.
- Do not add inner testbench/corner parallelism.
- Do not rename the user-facing `opt_requirement.md` field in this task.
- Do not change `threads_per_run` behavior.
- Do not hide failures by weakening validation for fields that Spectre/OCEAN actually use.

## Task 1: Prepared Manifest Removes Fake Spectre Parallelism

**Files:**

- Modify: `tests/test_real_run.py`
- Modify: `src/hermes_workflow/real_run.py`

**Step 1: Write the failing test**

Add a test that prepares a real run from a project with `spectre.parallel_jobs` in config and asserts:

```python
manifest = json.loads((run_dir / "real_run_manifest.json").read_text())
assert "parallel_jobs" not in manifest["spectre"]
assert manifest["spectre"]["threads_per_run"] == 10
assert manifest["spectre"]["timeout_s"] == 3600
```

The test must also assert that `config/spectre.yaml` still contains `parallel_jobs`, proving the input is preserved.

**Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/test_real_run.py::test_prepare_real_run_omits_parallel_jobs_from_spectre_runtime_contract -q
```

Expected: FAIL because the prepared manifest currently includes `spectre.parallel_jobs`.

**Step 3: Implement minimal code**

In `src/hermes_workflow/real_run.py`, remove `"parallel_jobs": spectre.parallel_jobs` from the prepared manifest `spectre` block.

Do not change `config/spectre.yaml`.

**Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/test_real_run.py::test_prepare_real_run_omits_parallel_jobs_from_spectre_runtime_contract -q
```

Expected: PASS.

- [ ] Commit with message: `fix: remove scheduler parallelism from prepared spectre metadata`

## Task 2: Metric Request Removes Fake Spectre Parallelism

**Files:**

- Modify: `tests/test_metric_requests.py`
- Modify: `src/hermes_workflow/metric_requests.py`

**Step 1: Write the failing test**

Add a test for `build_metric_extraction_request()` or the existing real-run request creation path:

```python
request = json.loads((run_dir / "metric_extraction_request.json").read_text())
assert "parallel_jobs" not in request["spectre"]
assert request["spectre"]["output_format"] == "psfxl"
assert request["spectre"]["threads_per_run"] == 10
assert request["spectre"]["timeout_s"] == 3600
```

**Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/test_metric_requests.py::test_metric_request_omits_parallel_jobs_from_spectre_runtime_contract -q
```

Expected: FAIL because the request currently includes `spectre.parallel_jobs`.

**Step 3: Implement minimal code**

In `src/hermes_workflow/metric_requests.py`, remove `"parallel_jobs": spectre.parallel_jobs` from the request `spectre` block.

**Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/test_metric_requests.py::test_metric_request_omits_parallel_jobs_from_spectre_runtime_contract -q
```

Expected: PASS.

- [ ] Commit with message: `fix: remove scheduler parallelism from metric request spectre metadata`

## Task 3: Adapter Preconditions Stop Requiring `spectre.parallel_jobs`

**Files:**

- Modify: `tests/test_spectre_ocean_adapter.py`
- Modify: `tests/test_remote_spectre_ocean.py`
- Modify: `src/hermes_workflow/execution_adapters/spectre_ocean.py`

**Step 1: Write failing tests**

Add a local adapter context test where prepared/request `spectre` blocks omit `parallel_jobs` and `load_adapter_context()` succeeds.

Add a remote adapter test where prepared/request omit `parallel_jobs` and `run_remote_spectre_ocean_adapter()` succeeds with the fake runner.

Also add a mismatch test proving real child runtime fields are still enforced:

```python
request["spectre"]["threads_per_run"] = 99
with pytest.raises(AdapterPreconditionError, match="spectre.threads_per_run"):
    load_adapter_context(project_dir, run_id="real_001")
```

**Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py::test_adapter_accepts_missing_parallel_jobs_in_spectre_contract tests/test_remote_spectre_ocean.py::test_remote_adapter_accepts_missing_parallel_jobs_in_spectre_contract -q
```

Expected: FAIL because adapter validation currently requires `spectre.parallel_jobs`.

**Step 3: Implement minimal code**

In `src/hermes_workflow/execution_adapters/spectre_ocean.py`:

- Remove the required positive-integer validation for `spectre.parallel_jobs`.
- Remove `"parallel_jobs"` from `_validate_spectre_settings_match()` matched keys.
- Keep validation and matching for `engine`, `preset`, `output_format`, `threads_per_run`, and `timeout_s`.

**Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest tests/test_spectre_ocean_adapter.py tests/test_remote_spectre_ocean.py -q
```

Expected: PASS.

- [ ] Commit with message: `fix: stop validating scheduler parallelism as spectre runtime metadata`

## Task 4: Preserve Scheduler Concurrency Behavior

**Files:**

- Modify: `tests/test_openbox_backend.py`
- Modify: `tests/test_native_turbo.py`
- Inspect only unless tests fail: `src/hermes_workflow/openbox_backend.py`
- Inspect only unless tests fail: `src/hermes_workflow/native_turbo.py`

**Step 1: Write or tighten tests**

Add/adjust tests proving:

```python
max_workers == min(config_parallel_jobs, optimizer_batch_size)
```

for OpenBox real evaluator setup.

Add/adjust equivalent native TuRBO test proving `parallel_jobs` still controls batch evaluator concurrency and does not depend on `spectre.parallel_jobs` inside prepared/request files.

**Step 2: Run tests to verify current behavior**

Run:

```bash
./.venv/bin/python -m pytest tests/test_openbox_backend.py::test_openbox_real_uses_requirement_parallel_jobs_for_candidate_workers tests/test_native_turbo.py::test_native_turbo_uses_requirement_parallel_jobs_for_candidate_workers -q
```

Expected: PASS if existing code already preserves scheduler behavior. If a test fails, fix only the broken scheduler data path.

**Step 3: Minimal implementation if needed**

Only if tests fail:

- Keep reading `bundle.spectre.spectre.parallel_jobs` as the scheduler value for this task.
- Keep `max_workers=min(selected_parallel_jobs, selected_batch_size)`.
- Do not read `parallel_jobs` from prepared/request `spectre` metadata.

**Step 4: Run tests to verify pass**

Run:

```bash
./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_native_turbo.py -q
```

Expected: PASS.

- [ ] Commit with message: `test: lock scheduler parallelism behavior`

## Task 5: Reporting Names The Value As Scheduler Parallelism

**Files:**

- Modify: `tests/test_doctor_readiness.py`
- Modify: `tests/test_optimizer_task_package.py`
- Modify: `src/hermes_workflow/doctor_readiness.py`
- Modify: `src/hermes_workflow/optimizer_task_package.py`
- Modify: `src/hermes_workflow/remote_doctor.py`
- Modify: `skills/ic-opt/SKILL.md`
- Modify: `src/hermes_workflow/agent_skills/ic-opt/SKILL.md`

**Step 1: Write failing tests**

Add doctor readiness tests asserting:

```python
summary["candidate_parallelism"] == 10
summary["inside_candidate_execution"] == "serial"
```

and no new report text calls this value a Spectre runtime field.

Add task package tests asserting the package records scheduler/candidate parallelism separately from `spectre_settings`.

**Step 2: Run tests to verify failure**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py tests/test_optimizer_task_package.py tests/test_agent_skill.py -q
```

Expected: FAIL where reports still expose `parallel_jobs` under `spectre_settings`.

**Step 3: Implement minimal code**

- Keep reading the config value from current config.
- Report it as `candidate_parallelism` or `scheduler.parallel_jobs`.
- Do not include it in task-package `spectre_settings`.
- Keep source and packaged `ic-opt` skill files identical.

**Step 4: Run tests to verify pass**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py tests/test_optimizer_task_package.py tests/test_agent_skill.py -q
```

Expected: PASS.

- [ ] Commit with message: `fix: report parallel jobs as scheduler parallelism`

## Task 6: Backlog And Documentation Update

**Files:**

- Modify: `docs/debug/2026-06-13-requirement-contract-backlog.md`
- Modify if needed: `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
- Modify if needed: `docs/USER_GUIDE_CN.md`

**Step 1: Update backlog status**

Set B-02 status to development-fixed only after tests pass. Include:

- `parallel_jobs` remains user-configurable.
- New prepared/request files omit `spectre.parallel_jobs`.
- Adapters tolerate old files but do not require the field.
- Candidate-level scheduler concurrency remains unchanged.

**Step 2: Update user docs only where they describe runtime meaning**

Replace any wording that implies `parallel_jobs` is a Spectre child-run parameter. Use:

```text
parallel_jobs controls the maximum number of candidates evaluated concurrently.
Inside one candidate, configured testbenches and corners run serially.
```

**Step 3: Run docs-related checks**

Run:

```bash
./.venv/bin/python -m pytest tests/test_agent_skill.py -q
git diff --check -- . ':!vendor' ':!.serena'
```

Expected: PASS.

- [ ] Commit with message: `docs: clarify scheduler parallelism contract`

## Task 7: Full Verification

**Files:** no code changes expected.

**Step 1: Run targeted tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_real_run.py tests/test_metric_requests.py tests/test_spectre_ocean_adapter.py tests/test_remote_spectre_ocean.py tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_doctor_readiness.py tests/test_optimizer_task_package.py tests/test_agent_skill.py -q
```

Expected: PASS.

**Step 2: Run full suite**

Run:

```bash
./.venv/bin/python -m pytest -q
```

Expected: PASS.

**Step 3: Run lint and whitespace checks**

Run:

```bash
./.venv/bin/python -m ruff check src tests
git diff --check -- . ':!vendor' ':!.serena'
```

Expected: PASS.

**Step 4: Real-flow validation before release sync**

Use `/home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_3` as the sample project.

Run a small remote multi-corner optimization. Verify:

- prepared manifest omits `spectre.parallel_jobs`;
- metric request omits `spectre.parallel_jobs`;
- doctor/report still shows configured candidate parallelism;
- scheduler trace or process observation confirms simultaneous Spectre process count is bounded by `min(batch_size, parallel_jobs)`;
- child testbench/corner runs remain serial inside each candidate.

- [ ] Commit with message: `test: validate scheduler parallelism contract`

## Task 8: Release Package Sync Gate

**Files:**

- Sync only after Task 7 passes: `../ic-auto-opt-workflow-v0.1`

**Step 1: Compare dev and release core files**

Run a file-level diff for modified source/test/doc files from this task.

**Step 2: Sync release package from dev**

Copy only validated changes required for release package parity. Do not invent release-only fixes.

**Step 3: Run release smoke tests**

At minimum run the targeted tests that exist in the release package and a doctor smoke on the sample project.

- [ ] Commit with message: `chore: sync scheduler parallelism contract to release package`
