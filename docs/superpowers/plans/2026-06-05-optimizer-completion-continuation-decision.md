# Optimizer Completion And Continuation Decision Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `hermes-workflow summarize-optimizer-run PROJECT_DIR`, a deterministic supervisor/Hermes report for deciding what to do after an accepted native TuRBO optimizer run.

**Architecture:** Reuse existing C-25 optimizer acceptance artifacts and native TuRBO trace files. The new checker reads accepted reports only, computes small deterministic evidence summaries, writes one `reports/optimizer_completion_report.json`, and never runs real tools or changes optimizer behavior.

**Tech Stack:** Python 3.11+, existing Hermes workflow modules, Typer CLI, pytest, ruff.

---

## Scope Guard

Allowed:

- read `reports/optimizer_run_acceptance_report.json`;
- read `reports/native_turbo_optimizer_report.json`;
- read `reports/native_turbo_optimizer_evaluations.jsonl`;
- read `config/variables.yaml` and `config/optimizer.yaml`;
- compute status counts, best observed candidate, search-space estimate, best-so-far improvement evidence, and one deterministic continuation decision;
- write `reports/optimizer_completion_report.json`;
- expose `hermes-workflow summarize-optimizer-run PROJECT_DIR`.

Forbidden:

- run Virtuoso, Spectre, OCEAN, SSH, `virtuoso-bridge-lite`, or an execution agent;
- run or modify TuRBO;
- generate optimizer candidates;
- implement continuation execution;
- implement exhaustive sweep execution;
- parse PSF or waveform data in Python;
- rewrite OCEAN formulas;
- change approved metrics, constraints, or objective formulas;
- claim global optimum unless trace coverage equals the full finite search space;
- add variable-result causal or LLM insight reporting in C-26.

## File Plan

- Create: `src/hermes_workflow/optimizer_completion.py`
  - Report model, artifact loader, search-space estimate, improvement summary, decision logic, and JSON writer.
- Modify: `src/hermes_workflow/cli.py`
  - Add `summarize-optimizer-run` command.
- Create: `tests/test_optimizer_completion.py`
  - Focused fake-artifact tests for continuation decisions and failure handling.
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: this plan file.

## Task 1: Report Model And Accepted Artifact Loader

**Risk:** Medium. Deterministic report/check logic, no real tools.

**Status:** Complete.

**Files:**

- Create: `src/hermes_workflow/optimizer_completion.py`
- Create: `tests/test_optimizer_completion.py`

- [x] **Step 1: Write failing accepted-run test**

Create `tests/test_optimizer_completion.py` with a fake project helper that writes:

```text
reports/optimizer_run_acceptance_report.json
reports/native_turbo_optimizer_report.json
reports/native_turbo_optimizer_evaluations.jsonl
config/variables.yaml
config/optimizer.yaml
```

The first test:

```python
def test_summarize_optimizer_run_loads_accepted_run(tmp_path: Path) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path)

    report = summarize_optimizer_run(project_dir)

    assert report.status == "pass"
    assert report.evaluation_count == 6
    assert report.best_observed["run_id"] == "real_006"
    assert report.status_counts == {"feasible": 4, "constraint_failed": 2}
    assert report.global_optimum_claim is False
    assert report.report_path == project_dir / "reports/optimizer_completion_report.json"
```

Run:

```bash
python3 -m pytest tests/test_optimizer_completion.py -q
```

Expected: fail because `hermes_workflow.optimizer_completion` does not exist.

- [x] **Step 2: Implement minimal report model and loader**

Create `src/hermes_workflow/optimizer_completion.py` with:

```python
REPORT_RELATIVE = Path("reports/optimizer_completion_report.json")
ACCEPTANCE_REPORT_RELATIVE = Path("reports/optimizer_run_acceptance_report.json")
NATIVE_REPORT_RELATIVE = Path("reports/native_turbo_optimizer_report.json")
NATIVE_EVALUATIONS_RELATIVE = Path("reports/native_turbo_optimizer_evaluations.jsonl")

@dataclass(frozen=True)
class OptimizerCompletionReport:
    status: str
    decision: str
    confidence: str
    global_optimum_claim: bool
    best_observed: dict[str, Any] | None
    evaluation_count: int
    status_counts: dict[str, int]
    search_space: dict[str, Any]
    improvement: dict[str, Any]
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    report_path: Path | None = None
```

Implement:

```python
def summarize_optimizer_run(project_dir: str | Path) -> OptimizerCompletionReport:
    ...
```

Task 1 minimum behavior:

- load acceptance report, native report, and JSONL trace;
- fail closed if acceptance report is missing or not `accepted`;
- count trace statuses;
- use native report `best_candidate` as `best_observed`;
- write `reports/optimizer_completion_report.json`;
- do not run tools or mutate optimizer artifacts.

- [x] **Step 3: Verify Task 1**

Run:

```bash
python3 -m pytest tests/test_optimizer_completion.py -q
python3 -m ruff check src/hermes_workflow/optimizer_completion.py tests/test_optimizer_completion.py
```

Expected: pass.

## Task 2: Decision Rules And Search-Space Evidence

**Risk:** Medium. Decision quality and supervisor-facing behavior.

**Status:** Complete.

**Files:**

- Modify: `src/hermes_workflow/optimizer_completion.py`
- Modify: `tests/test_optimizer_completion.py`

- [x] **Step 1: Add decision tests**

Add focused tests:

```python
def test_summarize_optimizer_run_recommends_continue_when_recent_best_improves(tmp_path: Path) -> None:
    ...

def test_summarize_optimizer_run_recommends_accept_when_trace_exhausts_space(tmp_path: Path) -> None:
    ...

def test_summarize_optimizer_run_recommends_exhaustive_when_space_is_small(tmp_path: Path) -> None:
    ...

def test_summarize_optimizer_run_recommends_stop_when_no_feasible_candidate_exists(tmp_path: Path) -> None:
    ...

def test_summarize_optimizer_run_fails_when_acceptance_rejected(tmp_path: Path) -> None:
    ...
```

Run:

```bash
python3 -m pytest tests/test_optimizer_completion.py -q
```

Expected: fail on missing decision logic.

- [x] **Step 2: Implement deterministic rules**

Implement these exact first-version rules:

1. If C-25 acceptance status is not `accepted`, write `status = fail`, `decision = stop_for_user_review`.
2. If no `feasible` trace row exists, choose `stop_for_user_review`.
3. Estimate finite search-space combinations from `config/variables.yaml`:
   - integer grid count: `upper - lower + 1`;
   - continuous-step grid count: `(upper - lower) / step + 1` when exact under `Decimal`;
   - otherwise unknown.
4. If `estimated_discrete_combinations == evaluation_count`, choose `accept_best_observed` and set `global_optimum_claim = true`.
5. If `estimated_discrete_combinations` is known and `estimated_discrete_combinations <= evaluation_count * 3`, choose `switch_to_exhaustive_sweep`.
6. Build best-so-far objective curve from finite trace `objective` values, minimizing objective.
7. Use `recent_window = min(20, max(5, evaluation_count // 5))`.
8. If best objective improved inside the recent window, choose `continue_more_evals`.
9. Otherwise choose `accept_best_observed`.

Do not add local-refinement neighborhood logic in C-26 Task 2. The enum may include `local_refine_around_best`, but first implementation should not select it until a later scoped feature defines neighborhood evidence.

- [x] **Step 3: Verify Task 2**

Run:

```bash
python3 -m pytest tests/test_optimizer_completion.py -q
python3 -m ruff check src/hermes_workflow/optimizer_completion.py tests/test_optimizer_completion.py
```

Expected: pass.

## Task 3: CLI Wiring And Focused Regression

**Risk:** Medium. CLI integration only.

**Status:** Complete.

**Files:**

- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_optimizer_completion.py`

- [x] **Step 1: Add CLI tests**

Add tests:

```python
def test_summarize_optimizer_run_cli_writes_report(tmp_path: Path) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path)

    result = runner.invoke(app, ["summarize-optimizer-run", str(project_dir)])

    assert result.exit_code == 0
    assert "optimizer completion summarized" in result.stdout
    assert "reports/optimizer_completion_report.json" in result.stdout
    assert (project_dir / "reports/optimizer_completion_report.json").exists()
```

and:

```python
def test_summarize_optimizer_run_cli_exits_nonzero_when_report_fails(tmp_path: Path) -> None:
    project_dir = _write_accepted_optimizer_project(tmp_path, accepted=False)

    result = runner.invoke(app, ["summarize-optimizer-run", str(project_dir)])

    assert result.exit_code == 1
    assert "optimizer completion failed" in result.stdout
```

Run:

```bash
python3 -m pytest tests/test_optimizer_completion.py -q
```

Expected: fail because CLI command does not exist.

- [x] **Step 2: Add CLI command**

In `src/hermes_workflow/cli.py`, import `summarize_optimizer_run` and add:

```python
@app.command("summarize-optimizer-run")
def summarize_optimizer_run_command(project_dir: Annotated[Path, typer.Argument(help="Project directory with accepted optimizer artifacts.")]) -> None:
    ...
```

Behavior:

- call `summarize_optimizer_run(project_dir)`;
- print `optimizer completion summarized` and the report path when `status == pass`;
- print `optimizer completion failed`, issues, and the report path when `status == fail`;
- exit `1` for failed report status.

- [x] **Step 3: Verify Task 3**

Run:

```bash
python3 -m pytest tests/test_optimizer_completion.py tests/test_optimizer_acceptance.py -q
python3 -m ruff check src/hermes_workflow/cli.py src/hermes_workflow/optimizer_completion.py tests/test_optimizer_completion.py
```

Expected: pass.

## Task 4: Docs, Final Verification, Commit

**Risk:** Low. Progress and completion bookkeeping.

**Status:** Complete.

**Files:**

- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: this plan file.

- [x] **Step 1: Mark C-26 complete in active files**

Update:

- this plan file checkboxes and task statuses;
- `docs/CURRENT_TASK_STATE.json`;
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`;
- `docs/EXECUTION_PROGRESS_2026-05-29.md`.

Keep `docs/COMPACT_RESUME_CHECKPOINT.md` unchanged unless the user asks for compaction or the resume prompt becomes stale.

- [x] **Step 2: Final verification**

Run:

```bash
python3 -m pytest tests/test_optimizer_completion.py tests/test_optimizer_acceptance.py tests/test_optimizer_task_package.py tests/test_native_turbo.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected: pass, with only intended tracked changes.

- [x] **Step 3: Commit**

Use explicit pathspecs:

```bash
git add \
  src/hermes_workflow/optimizer_completion.py \
  src/hermes_workflow/cli.py \
  tests/test_optimizer_completion.py \
  docs/CURRENT_TASK_STATE.json \
  docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md \
  docs/EXECUTION_PROGRESS_2026-05-29.md \
  docs/superpowers/plans/2026-06-05-optimizer-completion-continuation-decision.md
git commit -m "feat: add optimizer completion decision report"
```

## Self-Review

- Spec coverage: covers accepted-artifact loading, failure on rejected C-25 report, best observed summary, status distribution, finite search-space estimate, recent improvement evidence, deterministic decision output, CLI, and docs.
- Boundary check: no real tools, optimizer algorithm changes, continuation execution, exhaustive sweep execution, PSF parsing, formula rewrite, metric changes, or native-layout replacement.
- Deferred intentionally: variable-result insight report, local refinement execution, and LLM-generated design interpretation. These require separate practice evidence and should not be added to C-26.
