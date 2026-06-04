# OpenBox Production Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize the C-28 OpenBox ask-and-tell backend while preserving the existing Hermes Spectre/OCEAN execution path and TuRBO implementation.

**Architecture:** Add OpenBox real backend code inside `src/hermes_workflow/openbox_backend.py`, reuse existing Hermes quantization, real candidate package, Spectre/OCEAN checks, ledger recording, and backend-neutral artifacts. Add one CLI command, `run-openbox-real`, and keep C-25/C-26 as the supervisor audit and decision layer.

**Tech Stack:** Python, OpenBox optional dependency, existing Hermes workflow APIs, pytest, ruff.

---

## Boundaries

- Do not delete or replace `src/hermes_workflow/native_turbo.py`.
- Do not make OpenBox the default optimizer in C-29.
- Do not run real Virtuoso/Spectre/OCEAN until the dedicated real acceptance task.
- Do not add hidden constraints such as `FN=FP`.
- Do not parse PSF.
- Do not rewrite OCEAN formulas.
- Do not create a broad optimizer framework, daemon, database, or service.
- Do not commit raw Cadence artifacts.

## File Map

- Modify: `src/hermes_workflow/openbox_backend.py`
- Modify: `src/hermes_workflow/cli.py`
- Create or modify: `tests/test_openbox_backend.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Optional if real acceptance is confirmed: create sanitized note under `docs/debug/`

---

### Task 1: OpenBox Search Space Contract

**Files:**
- Modify: `src/hermes_workflow/openbox_backend.py`
- Create or modify: `tests/test_openbox_backend.py`

- [ ] **Step 1: Add failing tests for effective grid upper bounds**

Add tests that build an OpenBox space through an injected fake `space` module.
The tests must prove:

- `0.3u..3u step 0.2u` maps to effective OpenBox upper `2.9`.
- integer variables preserve their configured upper bound.
- `FN` and `FP` are independent variables.

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py::test_openbox_space_uses_effective_grid_upper -q
```

Expected: fail before implementation.

- [ ] **Step 2: Implement effective grid upper helper**

In `src/hermes_workflow/openbox_backend.py`, add a small helper equivalent to:

```python
def _effective_continuous_upper(lower: Decimal, upper: Decimal, step: Decimal) -> Decimal:
    max_offset = int((upper - lower) / step)
    return lower + Decimal(max_offset) * step
```

Use the helper only inside OpenBox space construction.

- [ ] **Step 3: Update OpenBox space construction**

Modify the existing OpenBox space builder so stepped continuous variables use
the effective upper. Keep the existing Hermes `quantize_candidate(...)` call as
the final parameter authority.

- [ ] **Step 4: Verify Task 1**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py::test_openbox_space_uses_effective_grid_upper -q
python3 -m pytest tests/test_openbox_backend.py -q
python3 -m ruff check src/hermes_workflow/openbox_backend.py tests/test_openbox_backend.py
```

Expected: all pass.

- [ ] **Step 5: Record Task 1**

Update `docs/CURRENT_TASK_STATE.json` with Task 1 completion and route audit.

---

### Task 2: Shared OpenBox Ask-And-Tell Runner Core

**Files:**
- Modify: `src/hermes_workflow/openbox_backend.py`
- Modify: `tests/test_openbox_backend.py`

- [ ] **Step 1: Add failing tests for batch ask-and-tell**

Write a fake advisor that returns deterministic suggestions and records
observations. Test that the runner core:

- requests suggestions by batch size
- quantizes through Hermes
- writes `selection_phase="openbox_batch"`
- writes backend-neutral report and JSONL paths
- reports duplicate replacement count

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py::test_openbox_runner_writes_backend_neutral_artifacts -q
```

Expected: fail before implementation.

- [ ] **Step 2: Add runner result model**

In `openbox_backend.py`, keep the existing `NativeTurboRunResult` trace shape
for compatibility. Add a narrow internal function:

```python
def _run_openbox_batches(...):
    ...
```

It must accept an evaluator callback that returns `NativeTurboObservation`.

- [ ] **Step 3: Add duplicate replacement**

Maintain a set of quantized parameter keys. If OpenBox returns a duplicate,
request replacement suggestions up to a bounded replacement budget. If the
budget is exhausted, raise `ValueError` before writing a false evaluation row.

- [ ] **Step 4: Write backend-neutral artifacts**

Use `reports/optimizer_run_report.json` and
`reports/optimizer_evaluations.jsonl`. The report must include:

```json
{
  "backend": "openbox",
  "execution_mode": "real or fake",
  "status": "completed",
  "evaluation_count": 100,
  "batch_summary": {
    "status_counts": {}
  },
  "openbox": {
    "random_seed": 20260528,
    "duplicate_replacements": 0
  }
}
```

- [ ] **Step 5: Verify Task 2**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py -q
python3 -m ruff check src/hermes_workflow/openbox_backend.py tests/test_openbox_backend.py
```

Expected: all pass.

- [ ] **Step 6: Record Task 2**

Update `docs/CURRENT_TASK_STATE.json` with Task 2 completion and route audit.

---

### Task 3: Real Candidate Evaluator Integration

**Files:**
- Modify: `src/hermes_workflow/openbox_backend.py`
- Modify: `tests/test_openbox_backend.py`

- [ ] **Step 1: Add failing tests for real evaluator integration**

Use fake adapter/evaluator functions; do not run real tools. Test that
`run_openbox_real_optimization(...)`:

- calls `prepare_explicit_candidate_real_run(...)` with
  `source="openbox_optimizer"`
- records metadata `optimizer="openbox"`
- executes through `execute_and_check_real_candidate(...)`
- records checked results through `record_real_result(...)`
- writes `execution_mode="real"`
- preserves `parallel_jobs` and `threads_per_run` in traces

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py::test_run_openbox_real_optimization_uses_existing_real_candidate_path -q
```

Expected: fail before implementation.

- [ ] **Step 2: Implement `run_openbox_real_optimization`**

Add:

```python
def run_openbox_real_optimization(
    project_dir: str | Path,
    *,
    max_evals: int,
    batch_size: int,
    parallel_jobs: int,
    cadence_cshrc: Path | None = None,
    advisor_factory: AdvisorFactory | None = None,
    adapter: Callable[..., object] | None = None,
) -> NativeTurboRunResult:
    ...
```

The function prepares batch candidates sequentially, executes checks through a
bounded thread pool, and records ledger/state sequentially.

- [ ] **Step 3: Keep fake backend compatible**

Refactor `run_openbox_fake_optimization(...)` to use the same runner core if
the refactor stays small. If sharing makes the file harder to read, keep the
fake runner separate and only share the space/observation/report helpers.

- [ ] **Step 4: Verify Task 3**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py -q
python3 -m pytest tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py -q
python3 -m ruff check src/hermes_workflow/openbox_backend.py tests/test_openbox_backend.py
```

Expected: all pass.

- [ ] **Step 5: Record Task 3**

Update `docs/CURRENT_TASK_STATE.json` with Task 3 completion and route audit.

---

### Task 4: CLI Wiring And Dependency Gate

**Files:**
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_openbox_backend.py` or CLI test file already used by the repo

- [ ] **Step 1: Add failing CLI tests**

Add tests for:

- `hermes-workflow run-openbox-real PROJECT_DIR --max-evals 4 --batch-size 2 --parallel-jobs 2`
- clear failure when OpenBox cannot be imported
- no real tools in tests; use monkeypatched backend entry point

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py::test_run_openbox_real_cli_delegates_to_backend -q
```

Expected: fail before implementation.

- [ ] **Step 2: Add CLI command**

Add a Typer command:

```python
@app.command("run-openbox-real")
def run_openbox_real_command(...):
    ...
```

It must print the report path and use the existing project path conventions.

- [ ] **Step 3: Verify Task 4**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py -q
python3 -m ruff check src/hermes_workflow/openbox_backend.py src/hermes_workflow/cli.py tests/test_openbox_backend.py
```

Expected: all pass.

- [ ] **Step 4: Record Task 4**

Update `docs/CURRENT_TASK_STATE.json` with Task 4 completion and route audit.

---

### Task 5: Local Contract Smoke Without Real Tools

**Files:**
- Modify: `tests/test_openbox_backend.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

- [ ] **Step 1: Add smoke fixture**

Use an existing lightweight project fixture. The smoke must generate OpenBox
backend-neutral artifacts without real tools and then run:

```bash
hermes-workflow check-optimizer-run PROJECT_DIR
hermes-workflow summarize-optimizer-run PROJECT_DIR
```

through test helpers or direct Python functions.

- [ ] **Step 2: Run focused smoke**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py -q
python3 -m pytest tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py -q
```

Expected: all pass.

- [ ] **Step 3: Run targeted regression**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py -q
python3 -m ruff check src/hermes_workflow/openbox_backend.py src/hermes_workflow/cli.py tests/test_openbox_backend.py
python3 tools/check_development_cadence.py
git diff --check
```

Expected: all pass.

- [ ] **Step 4: Record Task 5**

Update `docs/CURRENT_TASK_STATE.json` and
`docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`. Set next action to the real OpenBox
acceptance rerun only after user confirmation.

---

### Task 6: Real OpenBox Acceptance Rerun

**Files:**
- Local-only: `/tmp/ic_auto_opt_c29_openbox_real/`
- Create sanitized note only after a real run:
  `docs/debug/2026-06-05-c29-openbox-real-productization-acceptance.md`

- [ ] **Step 1: Wait for explicit real-tool confirmation**

Do not run this task until the user explicitly confirms real-tool execution for
C-29.

- [ ] **Step 2: Prepare clean local project**

Use the same native Maestro/ADE/Spectre layout as C-28 and C-24 retry. Ensure:

```text
netlists/exported/
netlists/templates/template.scs
config/
supervisor_instruction.json
```

are present, and old generated `runs/`, `reports/`, `state/`, and ledger rows
are absent.

- [ ] **Step 3: Run productized command**

Run:

```bash
csh -fc 'source /home/zzchen/cadence_ic231_env.csh; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; .venv/bin/hermes-workflow run-openbox-real /tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv --max-evals 100 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh'
```

Expected:

- 100 attempted evaluations unless a true setup/tool blocker occurs.
- backend-neutral optimizer artifacts exist.
- no hand-picked candidates.
- no hidden `FN=FP` coupling.

- [ ] **Step 4: Run C-25 and C-26**

Run:

```bash
.venv/bin/hermes-workflow check-optimizer-run /tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv
.venv/bin/hermes-workflow summarize-optimizer-run /tmp/ic_auto_opt_c29_openbox_real/bridge_test_inv
```

Expected: C-25 accepts and C-26 writes a decision report.

- [ ] **Step 5: Write sanitized evidence**

Write only sanitized counts, best observed candidate, settings audit, and
issues. Do not paste raw Cadence logs.

---

### Task 7: Final Closeout

**Files:**
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md` if the context is close to compaction

- [ ] **Step 1: Run final verification**

Run:

```bash
python3 -m pytest tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected: all checks pass; no raw local artifacts are staged.

- [ ] **Step 2: Commit**

Commit only source, tests, sanitized docs, and state updates:

```bash
git add src/hermes_workflow/openbox_backend.py src/hermes_workflow/cli.py tests/test_openbox_backend.py docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/EXECUTION_PROGRESS_2026-05-29.md
git commit -m "feat: add OpenBox real optimizer backend"
```

- [ ] **Step 3: Report**

Report:

- status
- changed files
- verification commands
- whether real acceptance was run
- remaining risks
- next recommended action

## Self-Review

- Spec coverage: all C-28 productization blockers are covered by Task 1 and
  Task 6.
- Hidden coupling: the plan explicitly keeps `FN`, `WN`, `FP`, and `WP`
  independent unless approved variables change.
- Real-tool boundary: code tasks use fake adapters; real execution is isolated
  to Task 6 after explicit confirmation.
- Artifact compatibility: Tasks 2, 3, 5, and 6 preserve C-25/C-26
  backend-neutral artifact compatibility.
