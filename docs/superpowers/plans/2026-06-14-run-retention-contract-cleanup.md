# B-06 Run Retention Contract Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for implementation and code review. Use `superpowers:test-driven-development` for every code change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `keep_failed_runs` and `keep_successful_runs` from `opt_requirement.md` enforce real local and remote run-directory retention after candidate finalization.

**Architecture:** Add one shared retention module that reads the existing validated Spectre settings, classifies candidate outcome, writes an immutable per-run retention decision report, and deletes only the candidate real-run directory when policy requires it. Local OpenBox/TuRBO call it after result checking and recording; remote flow wraps the injected remote adapter to clean the remote run directory after artifact download, while local cache cleanup still happens after local finalization.

**Tech Stack:** Python 3.11, Pydantic schemas, Typer CLI, pytest, local/remote Spectre/OCEAN adapters, OpenBox backend, native TuRBO backend.

## Guardrails

- Work only in `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`.
- Do not edit `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`.
- Do not add CLI flags for retention.
- Do not delete run directories before `check_real_run`, objective evaluation, aggregation, and `record_real_result` have consumed artifacts.
- Do not delete ledger, state, reports, config, source netlists, or templates.
- Treat constraint-failed candidates with valid metrics as successful observations for retention.
- Keep local and remote behavior aligned through shared policy code.

## Task 1: Add Shared Run Retention Core

**Files:**

- Create: `src/hermes_workflow/run_retention.py`
- Create: `tests/test_run_retention.py`

**Step 1: Write failing tests**

Create tests for:

- Loading policy from a project config with:

  ```yaml
  keep_failed_runs: false
  keep_successful_runs: true
  ```

- Successful run with `keep_successful_runs: true` keeps `runs/real/real_001`.
- Successful run with `keep_successful_runs: false` deletes `runs/real/real_001`.
- Failed run with `keep_failed_runs: true` keeps `runs/real/real_001`.
- Failed run with `keep_failed_runs: false` deletes `runs/real/real_001`.
- Cleanup always writes `state/run_retention/real_001.json`.
- Cleanup refuses unsafe run ids such as `../real_001` and does not delete outside `runs/real`.

Use a tiny fixture project or monkeypatch `assert_valid_project()` so the tests do not require real EDA tools.

**Step 2: Run tests to verify RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_run_retention.py -q
```

Expected: FAIL because `run_retention.py` does not exist.

**Step 3: Implement minimal core**

Implement:

- `RunRetentionPolicy`
- `RunRetentionDecision`
- `load_run_retention_policy(project_dir: Path) -> RunRetentionPolicy`
- `apply_local_run_retention(project_dir: Path, run_id: str, candidate_id: str | None, run_succeeded: bool) -> RunRetentionDecision`

Implementation requirements:

- Read `bundle.spectre.spectre.keep_failed_runs` and `keep_successful_runs` from `assert_valid_project(project_dir)`.
- Only allow run ids matching the existing real-run id pattern used by optimizer runs.
- Only delete `project_dir / "runs" / "real" / run_id`.
- Write `state/run_retention/<run_id>.json` before returning.
- If deletion is requested and fails, return/report `local_action="failed"` with the exception message in `issues`.

**Step 4: Run tests to verify GREEN**

Run:

```bash
./.venv/bin/python -m pytest tests/test_run_retention.py -q
```

Expected: PASS.

- [ ] Commit with message: `fix: add run retention policy core`

## Task 2: Apply Retention In Local Candidate Finalization

**Files:**

- Modify: `src/hermes_workflow/native_turbo.py`
- Modify: `src/hermes_workflow/openbox_backend.py` only if OpenBox does not already pass through the native finalization path.
- Modify: `tests/test_native_turbo.py`
- Modify: `tests/test_openbox_backend.py`

**Step 1: Write failing tests**

Add tests that run the real-candidate path with fake adapters:

- `keep_successful_runs: false` with a successful metric result:
  - `ledger/experiment_ledger.jsonl` exists and includes the observation.
  - `state/optimizer_state.json` exists.
  - `state/run_retention/<run_id>.json` exists with `run_status="successful"` and `local_action="deleted"`.
  - `runs/real/<run_id>` no longer exists.
- `keep_successful_runs: true` keeps the run directory.
- `keep_failed_runs: false` with an adapter/check failure removes the run directory and writes `run_status="failed"`.
- A constraint-failed but metric-valid result is classified as `run_status="successful"`.

**Step 2: Run tests to verify RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_native_turbo.py tests/test_openbox_backend.py -q
```

Expected: FAIL because no retention call exists after candidate finalization.

**Step 3: Implement local integration**

In `native_turbo.evaluate_real_candidate()` / `execute_and_check_real_candidate()` finalization flow:

- Do not call retention before adapter result checking.
- Do not call retention before `record_real_result()` for usable observations.
- After the candidate outcome is known, call `apply_local_run_retention(...)`.
- Use `run_succeeded=True` when the optimizer has a usable real observation, including `real_constraint_fail`.
- Use `run_succeeded=False` for workflow failures, adapter failures, metric failures, and record failures.
- If retention action is `failed` when deletion was requested, surface the issue in the returned observation or raise a clear workflow failure.

OpenBox should continue to reuse this path. If a separate OpenBox finalization path bypasses it, add the same call there using the shared helper.

**Step 4: Run tests to verify GREEN**

Run:

```bash
./.venv/bin/python -m pytest tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_run_retention.py -q
```

Expected: PASS.

- [ ] Commit with message: `fix: enforce local run retention after candidate finalization`

## Task 3: Apply Retention To Remote Run Directories

**Files:**

- Modify: `src/hermes_workflow/run_retention.py`
- Modify: `src/hermes_workflow/remote_optimizer_flow.py`
- Modify: `tests/test_remote_optimizer_flow.py`
- Modify: `tests/test_remote_spectre_ocean.py` only if existing remote adapter tests need expectation updates.

**Step 1: Write failing tests**

Add fake SSH runner tests proving:

- For a remote single-testbench run with `keep_successful_runs: false`, remote cleanup runs after `run_remote_spectre_ocean_adapter()` returns and uses the exact remote run path.
- For a remote multi-testbench/multi-corner run with `keep_successful_runs: false`, remote cleanup runs once for the parent run root after `run_remote_multi_testbench_adapter()` returns, not after each child.
- For `keep_failed_runs: false`, remote cleanup runs after a failed adapter result.
- When the relevant keep flag is `true`, no remote delete command is issued.
- Remote cleanup command contains no glob and is constrained under the remote project directory.

**Step 2: Run tests to verify RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_remote_spectre_ocean.py -q
```

Expected: FAIL because remote retention is not applied.

**Step 3: Implement remote integration**

Add to `run_retention.py`:

- `apply_remote_run_retention(ref, runner, run_id, candidate_id, run_succeeded, policy) -> RunRetentionDecision`

In `remote_optimizer_flow.optimize_remote_project()`:

- Keep remote flow as adapter injection.
- Build one `selected_adapter(local_project, run_id, cadence_cshrc)` wrapper.
- Inside the wrapper, choose the existing remote adapter:
  - single testbench: `run_remote_spectre_ocean_adapter`
  - multi-testbench or multi-corner: `run_remote_multi_testbench_adapter`
- After the adapter returns and artifacts have been downloaded, call `apply_remote_run_retention(...)`.
- Do not duplicate optimizer, OpenBox, or TuRBO logic in remote flow.
- Do not clean the local cache here; local cleanup remains after candidate finalization.

**Step 4: Run tests to verify GREEN**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_remote_spectre_ocean.py tests/test_run_retention.py -q
```

Expected: PASS.

- [ ] Commit with message: `fix: enforce remote run retention policy`

## Task 4: Add Doctor And Report Visibility

**Files:**

- Modify: `src/hermes_workflow/doctor_readiness.py`
- Modify: `src/hermes_workflow/product_doctor.py` only if payload mapping needs adjustment.
- Modify: `src/hermes_workflow/remote_doctor.py` only if payload mapping needs adjustment.
- Modify: `tests/test_doctor_readiness.py`
- Modify: `tests/test_product_doctor.py`
- Modify: `tests/test_remote_doctor.py`

**Step 1: Write failing tests**

Add tests asserting local and remote doctor JSON includes:

```json
"run_retention": {
  "keep_failed_runs": false,
  "keep_successful_runs": true,
  "cleanup_scope": "runs/real/<run_id>",
  "decision_reports": "state/run_retention/<run_id>.json"
}
```

The exact shape can live under `resource_summary` or a new top-level `retention_summary`, but it must be the same for local and remote doctor payloads.

**Step 2: Run tests to verify RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py tests/test_product_doctor.py tests/test_remote_doctor.py -q
```

Expected: FAIL because doctor does not report retention policy.

**Step 3: Implement minimal reporting**

Use existing parsed requirement sections. Do not reparse `opt_requirement.md`.

Add a summary helper to `doctor_readiness.py` that reads:

- `Spectre Settings.keep_failed_runs`
- `Spectre Settings.keep_successful_runs`

Expose the summary in both local and remote doctor outputs.

**Step 4: Run tests to verify GREEN**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py tests/test_product_doctor.py tests/test_remote_doctor.py -q
```

Expected: PASS.

- [ ] Commit with message: `docs: report run retention policy in doctor`

## Task 5: Documentation And Backlog Update

**Files:**

- Modify: `docs/debug/2026-06-13-requirement-contract-backlog.md`
- Modify: `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
- Modify: `docs/USER_GUIDE_CN.md`
- Modify: `docs/TROUBLESHOOTING_CN.md` only if it already discusses real run artifacts.
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md` only to clarify comments; do not change field names.

**Step 1: Update backlog**

Change B-06 status from open to development-fixed only after implementation tests pass. Before implementation is complete, mark it planned and reference this spec/plan.

**Step 2: Update user-facing retention semantics**

Document:

```text
keep_successful_runs controls whether successful candidate run directories under runs/real/<run_id> are kept after the result has been recorded.
keep_failed_runs controls whether failed candidate run directories are kept for debug.
Constraint-failed candidates with valid metrics are successful optimizer observations and use keep_successful_runs.
Ledger, state, best-candidate, optimizer reports, and state/run_retention/<run_id>.json are retained regardless of these settings.
```

**Step 3: Run docs checks**

Run:

```bash
git diff --check -- . ':!vendor' ':!.serena'
```

Expected: PASS.

- [ ] Commit with message: `docs: clarify run retention contract`

## Task 6: Full Verification

**Step 1: Run targeted tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_run_retention.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_optimizer_flow.py tests/test_remote_spectre_ocean.py tests/test_doctor_readiness.py tests/test_product_doctor.py tests/test_remote_doctor.py -q
```

Expected: PASS.

**Step 2: Run full test suite**

Run:

```bash
./.venv/bin/python -m pytest -q
```

Expected: PASS.

**Step 3: Run lint**

Run:

```bash
./.venv/bin/python -m ruff check src tests
```

Expected: PASS.

**Step 4: Run whitespace check**

Run:

```bash
git diff --check -- . ':!vendor' ':!.serena'
```

Expected: PASS.

**Step 5: Real-flow validation before release sync**

Use `/home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_3` only after unit/targeted/full tests pass.

Run a small remote smoke with:

- one config where both keep flags are `true`; confirm local and remote run dirs remain.
- one config where `keep_successful_runs: false`; confirm successful local cache and remote run dirs are removed only after result/state/report are written.
- one intentionally failing run or fake-safe failure path with `keep_failed_runs: false`; confirm failed run dirs are removed and retention decision report remains.

Do not run the 80-point optimization until this retention smoke passes.

## Task 7: Release Sync Gate

Release sync is not part of B-06 implementation.

Before any sync to `ic-auto-opt-workflow-v0.1`, produce a dev verification report containing:

- modified files
- test commands and results
- real-flow validation result
- confirmation that no release files were edited during development
- remaining risks
