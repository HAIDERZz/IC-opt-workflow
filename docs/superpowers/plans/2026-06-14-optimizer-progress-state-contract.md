# B-09 Optimizer Progress State Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for implementation and review checkpoints. Use `superpowers:test-driven-development` for every code change. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Goal:** Make optimizer progress artifacts agree by defining `state/optimizer_state.json` as attempted-evaluation progress while keeping the ledger as usable recorded observations.
>
> **Architecture:** Add one shared optimizer progress-state module that builds state from optimizer report/evaluation traces plus ledger counts. Call it from both OpenBox and native TuRBO report writers so local and remote share the same contract. Extend doctor/readiness to detect state/report/evaluations/ledger mismatches instead of silently accepting split progress.
>
> **Tech Stack:** Python 3.11, Pydantic schemas, pytest, OpenBox backend, native TuRBO backend, existing optimizer artifacts/report loaders.

Guardrails:

- Work only in `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`.
- Do not edit `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`.
- Do not add CLI flags.
- Do not fake progress by padding `ledger/experiment_ledger.jsonl` with failed rows.
- Do not require `state/best_candidate.json` when no feasible candidate exists.
- Preserve local/remote parity by changing shared optimizer/report code, not by adding separate remote behavior.

## Task 1: Add Progress-State Contract Tests And Schema Fields

**Files:**

- Modify: `src/hermes_workflow/schemas.py`
- Create: `tests/test_optimizer_progress_state.py`

**Step 1: Write the failing schema/contract test**

Create tests that construct a minimal optimizer project with:

- `reports/optimizer_run_report.json` containing `status: "completed"` and `evaluation_count: 10`
- `reports/optimizer_evaluations.jsonl` containing 10 traces:
  - 7 with status `constraint_failed`
  - 3 with status `metric_check_failed`
- `ledger/experiment_ledger.jsonl` containing 7 rows
- no `state/best_candidate.json`

The test must assert that the future sync helper writes:

```json
{
  "current_evaluations": 10,
  "recorded_observation_count": 7,
  "failed_evaluation_count": 3,
  "status_counts": {
    "constraint_failed": 7,
    "metric_check_failed": 3
  },
  "progress_source": "reports/optimizer_evaluations.jsonl",
  "best_candidate_id": null,
  "status": "completed"
}
```

**Step 2: Run the test to verify RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_optimizer_progress_state.py -q
```

Expected: FAIL because `optimizer_progress_state.py` and new `OptimizerState` fields do not exist.

**Step 3: Extend `OptimizerState` minimally**

Add optional/default fields to `OptimizerState`:

- `recorded_observation_count: StrictInt | None = None`
- `failed_evaluation_count: StrictInt | None = None`
- `status_counts: dict[str, StrictInt] = Field(default_factory=dict)`
- `progress_source: str | None = None`

Keep existing fields backward compatible. Do not remove or rename `current_evaluations`.

**Step 4: Run the test again**

Run:

```bash
./.venv/bin/python -m pytest tests/test_optimizer_progress_state.py -q
```

Expected: still FAIL because the helper implementation is not present.

- [ ] Commit schema/test RED if committing is allowed by the user.

## Task 2: Implement Shared Progress-State Sync

**Files:**

- Create: `src/hermes_workflow/optimizer_progress_state.py`
- Modify: `tests/test_optimizer_progress_state.py`

**Step 1: Implement helper API**

Create:

```python
def sync_optimizer_progress_state(project_dir: Path) -> Path:
    ...
```

The helper must:

- read `reports/optimizer_run_report.json`
- read `reports/optimizer_evaluations.jsonl`
- count rows in `ledger/experiment_ledger.jsonl` if present
- read existing `state/best_candidate.json` if present
- write `state/optimizer_state.json`

Use existing project validation/config helpers to obtain:

- project name
- optimizer algorithm
- initialization
- `max_evaluations`
- `batch_size`
- `random_seed`

If validation is too heavy for unit tests, isolate a pure function such as:

```python
def build_optimizer_progress_state(...) -> OptimizerState:
    ...
```

and make `sync_optimizer_progress_state()` perform file IO.

**Step 2: Define counting rules**

Rules:

- `attempted_count = len(optimizer_evaluations.jsonl rows)`.
- `report_count = optimizer_run_report.evaluation_count`.
- If both exist and disagree, record an issue in a sidecar diagnostic or raise a clear `ValueError`.
- `recorded_observation_count = ledger row count`.
- `failed_evaluation_count = max(0, attempted_count - recorded_observation_count)`.
- `current_evaluations = attempted_count`.
- `status_counts = Counter(trace["status"] for trace in traces)`.
- `status = "completed"` when report status is completed and attempted count reached budget or report has `completed_early: true`; otherwise keep `running`.
- `best_candidate_id = existing best candidate id if present else None`.

**Step 3: Run unit tests to verify GREEN**

Run:

```bash
./.venv/bin/python -m pytest tests/test_optimizer_progress_state.py -q
```

Expected: PASS.

- [ ] Commit with `fix: define optimizer progress state contract` if committing is allowed by the user.

## Task 3: Wire Progress Sync Into OpenBox And Native TuRBO Report Writers

**Files:**

- Modify: `src/hermes_workflow/openbox_backend.py`
- Modify: `src/hermes_workflow/native_turbo.py`
- Modify: `tests/test_openbox_backend.py`
- Modify: `tests/test_native_turbo.py`

**Step 1: Write failing integration tests**

Add tests that call the actual report-writing functions:

- `write_openbox_reports(...)`
- `write_native_turbo_reports(...)`

Each test must provide 10 traces, 7 recorded observations, and 3 failed traces. After report writing, assert:

- `reports/optimizer_run_report.json` has `evaluation_count: 10`
- `reports/optimizer_evaluations.jsonl` has 10 rows
- `state/optimizer_state.json.current_evaluations == 10`
- `state/optimizer_state.json.recorded_observation_count == 7`
- `state/optimizer_state.json.failed_evaluation_count == 3`
- no feasible best does not force `state/best_candidate.json`

**Step 2: Run the tests to verify RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_native_turbo.py -q
```

Expected: FAIL because report writers do not yet call progress sync.

**Step 3: Call the shared sync helper**

After each writer finishes writing report/evaluations/effectiveness artifacts, call:

```python
sync_optimizer_progress_state(project_dir)
```

Do this in both writers. Do not duplicate counting logic in either backend.

**Step 4: Run targeted tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_optimizer_progress_state.py tests/test_openbox_backend.py tests/test_native_turbo.py -q
```

Expected: PASS.

- [ ] Commit with `fix: sync optimizer state from OpenBox and TuRBO traces` if committing is allowed by the user.

## Task 4: Add Doctor Consistency Diagnostics

**Files:**

- Modify: `src/hermes_workflow/doctor_readiness.py`
- Modify: `src/hermes_workflow/product_doctor.py` only if payload wiring requires it
- Modify: `src/hermes_workflow/remote_doctor.py` only if payload wiring requires it
- Modify: `tests/test_doctor_readiness.py`
- Modify: `tests/test_product_doctor.py`
- Modify: `tests/test_remote_doctor.py`

**Step 1: Write failing diagnostics tests**

Add tests for a project where:

- report `evaluation_count` is 10
- evaluations JSONL has 10 rows
- `state/optimizer_state.json.current_evaluations` is 7
- ledger has 7 rows

Expected doctor semantic diagnostics include an error or warning code such as:

```text
OPTIMIZER_PROGRESS_STATE_MISMATCH
```

The diagnostic must identify the mismatched values.

Also add a passing test where:

- report count is 10
- evaluations count is 10
- state current count is 10
- state recorded count is 7
- ledger count is 7

Expected: no progress mismatch diagnostic.

**Step 2: Run diagnostics tests to verify RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py tests/test_product_doctor.py tests/test_remote_doctor.py -q
```

Expected: FAIL because doctor does not compare artifact counts.

**Step 3: Implement consistency summary**

In `doctor_readiness.py`, add a shared helper that reads existing artifacts if present and reports:

- `report_evaluation_count`
- `evaluation_trace_count`
- `state_current_evaluations`
- `state_recorded_observation_count`
- `ledger_row_count`
- `failed_evaluation_count`
- `status_counts`

Add structured diagnostics when counts disagree. Reuse this helper for local and remote doctor payloads. Do not duplicate requirement parsing.

**Step 4: Run diagnostics tests to verify GREEN**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py tests/test_product_doctor.py tests/test_remote_doctor.py -q
```

Expected: PASS.

- [ ] Commit with `fix: diagnose optimizer progress state drift` if committing is allowed by the user.

## Task 5: Verify Remote/Local Artifact Sync Semantics

**Files:**

- Modify: `tests/test_remote_optimizer_flow.py` only if current tests do not assert state upload/download
- Modify: `src/hermes_workflow/remote_optimizer_flow.py` only if tests prove remote closeout does not carry updated state

**Step 1: Write or extend a remote-flow test**

Use the fake SSH runner to assert that after remote optimizer completion, the updated `state/optimizer_state.json` is included wherever existing report/state sync copies artifacts.

Expected remote/local parity:

- local cache state has attempted count
- remote project state has attempted count
- report/evaluations/state are all present

**Step 2: Run the test to verify RED or confirm existing behavior**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py -q
```

If it passes without implementation changes, document that existing sync already carries the corrected state. If it fails, fix only the missing artifact sync path.

**Step 3: Run remote-flow tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_optimizer_progress_state.py -q
```

Expected: PASS.

- [ ] Commit with `fix: preserve optimizer progress state in remote sync` only if code changes were required.

## Task 6: Update B-09 Documentation And Backlog

**Files:**

- Modify: `docs/debug/2026-06-13-requirement-contract-backlog.md`
- Modify: `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md` only if the current user docs describe old state semantics
- Modify: `docs/TROUBLESHOOTING_CN.md` only if progress troubleshooting needs the new fields

**Step 1: Update B-09 status**

Set B-09 from `open` to `implemented` only after code and tests pass. While implementing, use `in_progress`.

**Step 2: Document progress semantics**

Document:

- `current_evaluations` means attempted optimizer evaluations
- `recorded_observation_count` means usable ledger observations
- `failed_evaluation_count` means attempted minus recorded
- missing `best_candidate.json` is valid when no feasible candidate exists

**Step 3: Run documentation checks**

Run:

```bash
git diff --check -- . ':!vendor' ':!.serena'
```

Expected: no whitespace errors.

- [ ] Commit with `docs: document optimizer progress state contract` if committing is allowed by the user.

## Task 7: Full Verification

**Step 1: Run targeted tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_optimizer_progress_state.py tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_doctor_readiness.py tests/test_product_doctor.py tests/test_remote_doctor.py tests/test_remote_optimizer_flow.py -q
```

Expected: PASS.

**Step 2: Run full suite**

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

**Step 4: Run diff check**

Run:

```bash
git diff --check -- . ':!vendor' ':!.serena'
```

Expected: PASS.

**Step 5: Report real validation readiness**

Do not claim real local/remote validation is complete unless those flows were actually run. If real runs were not run, report that explicitly and list the exact commands needed.

- [ ] Final implementation report includes modified files, RED/GREEN evidence, verification commands, and whether release package was untouched.
