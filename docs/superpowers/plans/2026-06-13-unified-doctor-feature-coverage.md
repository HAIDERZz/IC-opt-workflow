# C-78 Unified Doctor Feature Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not use subagents unless the user explicitly asks for them. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete product doctor coverage for local and remote projects so doctor audits multi-corner setup, optimizer strategy, resources, budget precedence, and dirty run state before real optimization.

**Architecture:** Keep `ic-opt` as the only product CLI. Add a small shared doctor readiness helper used by both local and remote doctor paths. Remote doctor remains transport-specific only for SSH, remote file access, remote tool checks, and cache preparation; semantic checks run through the shared core.

**Tech Stack:** Python 3.11, Typer, Pydantic config schemas, existing `RequirementIntakeReport`, `OptimizerStrategyName`, `resolve_optimizer_strategy`, `RemoteSshRunner`, `prepare_remote_project_cache`, pytest, ruff.

## Hard Constraints

- Development happens in `ic-auto-opt-workflow`.
- Do not develop directly in `ic-auto-opt-workflow-v0.1`.
- Do not run Spectre, OCEAN, Virtuoso, OpenBox, or TuRBO from doctor tests.
- Do not add `--multi-corner`, `--local-doctor`, or `--remote-doctor`.
- Do not change real optimizer adapter semantics.
- Do not change candidate/testbench/corner execution concurrency.
- Do not rewrite formulas, objective expressions, or PDK corner data.
- Do not add another requirement parser for remote mode.

## Task 1: Shared Doctor Readiness Summary

**Files:**

- Create: `src/hermes_workflow/doctor_readiness.py`
- Create: `tests/test_doctor_readiness.py`
- Modify only if needed: `src/hermes_workflow/__init__.py`

**Step 1: Write tests for requirement and matrix summaries**

Create `tests/test_doctor_readiness.py` with tests that build minimal section
dictionaries and assert:

```python
from hermes_workflow.doctor_readiness import build_requirement_summary


def test_requirement_summary_reports_nominal_defaults():
    summary = build_requirement_summary(
        {
            "Design Variables": [{"name": "W", "lower": "1u", "upper": "10u"}],
            "Metrics": [{"name": "gain"}],
            "Objective": {"expression": "-gain"},
            "Spectre Settings": {"parallel_jobs": 4},
        }
    )
    assert summary["has_process_corners"] is False
    assert summary["corner_count"] == 1
    assert summary["testbench_count"] == 1
    assert summary["child_runs_per_candidate"] == 1
    assert summary["inside_candidate_execution"] == "serial"


def test_requirement_summary_reports_multi_tb_multi_corner_matrix():
    summary = build_requirement_summary(
        {
            "Testbenches": [
                {"id": "gain_tb", "maestro_view": "gain"},
                {"id": "noise_tb", "maestro_view": "noise"},
            ],
            "Process Corners": {
                "objective_policy": "worst_case",
                "constraint_policy": "all_corners",
                "corners": [
                    {"id": "tt", "model_section": "tt"},
                    {"id": "ss", "model_section": "ss"},
                    {"id": "ff", "model_section": "ff"},
                ],
            },
            "Spectre Settings": {"parallel_jobs": 4},
        }
    )
    assert summary["has_process_corners"] is True
    assert summary["corner_count"] == 3
    assert summary["testbench_count"] == 2
    assert summary["child_runs_per_candidate"] == 6
    assert summary["objective_policy"] == "worst_case"
    assert summary["constraint_policy"] == "all_corners"
```

**Step 2: Run tests to verify failure**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py -q
```

Expected: FAIL because `hermes_workflow.doctor_readiness` does not exist.

**Step 3: Implement `doctor_readiness.py`**

Implement pure helpers:

```python
def build_requirement_summary(sections: dict[str, object]) -> dict[str, object]:
    ...


def build_evaluation_matrix_summary(sections: dict[str, object]) -> dict[str, object]:
    ...
```

Rules:

- no `Testbenches` section means `testbench_count=1`;
- no `Process Corners` section means `corner_count=1`, `objective_policy="nominal"`, `constraint_policy="nominal"`;
- explicit one-corner config is preserved as explicit single-corner state;
- `child_runs_per_candidate = testbench_count * corner_count`;
- `inside_candidate_execution = "serial"`;
- `candidate_parallelism` comes from `Spectre Settings.parallel_jobs` when present.

**Step 4: Run tests to verify pass**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py -q
```

Expected: PASS.

- [ ] Commit with message: `feat: add shared doctor readiness summaries`

## Task 2: Optimizer And Budget Summary

**Files:**

- Modify: `src/hermes_workflow/doctor_readiness.py`
- Modify: `tests/test_doctor_readiness.py`

**Step 1: Write tests for optimizer strategy summaries**

Add tests:

```python
from hermes_workflow.doctor_readiness import build_optimizer_summary


def test_optimizer_summary_resolves_prf_eic_strategy():
    summary = build_optimizer_summary(
        optimizer_section={
            "algorithm": "openbox",
            "strategy": "openbox_prf_eic",
            "max_evaluations": 80,
        },
        variable_count=11,
        cli_max_evals=None,
    )
    assert summary["algorithm"] == "openbox"
    assert summary["requested_strategy"] == "openbox_prf_eic"
    assert summary["resolved_backend"] == "openbox"
    assert summary["surrogate_type"] == "prf"
    assert summary["acq_type"] == "eic"
    assert summary["acq_optimizer_type"] == "local_random"
    assert summary["initial_trials"] == 22
    assert summary["max_evaluations"] == 80
    assert summary["max_evaluations_source"] == "config"


def test_optimizer_summary_reports_cli_budget_override():
    summary = build_optimizer_summary(
        optimizer_section={"algorithm": "openbox", "max_evaluations": 80},
        variable_count=4,
        cli_max_evals=3,
    )
    assert summary["max_evaluations"] == 3
    assert summary["max_evaluations_source"] == "cli"
```

**Step 2: Run tests to verify failure**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py -q
```

Expected: FAIL because optimizer summary helper does not exist.

**Step 3: Implement optimizer summary**

Implement:

```python
def build_optimizer_summary(
    *,
    optimizer_section: dict[str, object],
    variable_count: int,
    cli_max_evals: int | None,
) -> dict[str, object]:
    ...
```

Use existing strategy resolver from `src/hermes_workflow/optimizer_strategy.py`.

Budget source rules:

- `cli` if `cli_max_evals is not None`;
- `config` if `optimizer_section["max_evaluations"]` exists;
- `default` only if neither exists.

Do not create new optimizer strategy names.

**Step 4: Run tests to verify pass**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py tests/test_optimizer_strategy.py -q
```

Expected: PASS.

- [ ] Commit with message: `feat: report doctor optimizer strategy summary`

## Task 3: Dirty-State Summary

**Files:**

- Modify: `src/hermes_workflow/doctor_readiness.py`
- Modify: `tests/test_doctor_readiness.py`

**Step 1: Write tests for interrupted and continuation state**

Add tests:

```python
from hermes_workflow.doctor_readiness import build_dirty_state_summary


def test_dirty_state_warns_on_incomplete_real_run(tmp_path):
    project = tmp_path / "project"
    (project / "runs" / "real" / "real_001").mkdir(parents=True)
    summary, diagnostics = build_dirty_state_summary(project)
    assert summary["has_runs"] is True
    assert summary["has_incomplete_real_run"] is True
    assert any(item.code == "INCOMPLETE_REAL_RUN" for item in diagnostics)


def test_dirty_state_reports_optimizer_history(tmp_path):
    project = tmp_path / "project"
    (project / "state").mkdir(parents=True)
    (project / "state" / "optimizer_state.json").write_text("{}", encoding="utf-8")
    (project / "reports").mkdir(parents=True)
    (project / "reports" / "optimizer_evaluations.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    summary, diagnostics = build_dirty_state_summary(project)
    assert summary["has_optimizer_state"] is True
    assert summary["has_optimizer_evaluations"] is True
    assert diagnostics == []
```

**Step 2: Run tests to verify failure**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py -q
```

Expected: FAIL because dirty-state helper does not exist.

**Step 3: Implement dirty-state helper**

Implement:

```python
def build_dirty_state_summary(project_dir: Path) -> tuple[dict[str, object], list[Diagnostic]]:
    ...
```

Detect:

- `runs/real/*`;
- run directories without `reports/optimizer_run_report.json`,
  `reports/optimizer_completion_report.json`, or an equivalent existing
  completion artifact;
- `execution_package/`;
- `state/optimizer_state.json`;
- `reports/optimizer_run_report.json`;
- `reports/optimizer_evaluations.jsonl`.

Use warning diagnostics for interrupted run directories.

**Step 4: Run tests to verify pass**

Run:

```bash
./.venv/bin/python -m pytest tests/test_doctor_readiness.py -q
```

Expected: PASS.

- [ ] Commit with message: `feat: add doctor dirty-state summary`

## Task 4: Local Product Doctor Uses Shared Summary

**Files:**

- Modify: `src/hermes_workflow/product_doctor.py`
- Modify: `src/hermes_workflow/product_cli.py`
- Modify: `tests/test_product_doctor.py`
- Modify: `tests/test_product_cli.py`

**Step 1: Write product doctor report tests**

Add tests that run `run_product_doctor()` with fake services and assert report
payload contains:

```python
payload["transport"]["mode"] == "local"
payload["requirement_summary"]["corner_count"] == 3
payload["evaluation_matrix"]["child_runs_per_candidate"] == 3
payload["optimizer_summary"]["requested_strategy"] == "openbox_prf_eic"
payload["optimizer_summary"]["max_evaluations_source"] == "config"
payload["dirty_state"]["has_execution_package"] is False
```

Use a temporary project with `opt_requirement.md` and fake service returns so no
Spectre/OCEAN command runs.

**Step 2: Run tests to verify failure**

Run:

```bash
./.venv/bin/python -m pytest tests/test_product_doctor.py tests/test_product_cli.py -q
```

Expected: FAIL because local doctor report lacks new fields.

**Step 3: Extend `run_product_doctor()`**

In `product_doctor.py`:

- after requirement/config checks, read the parsed requirement/config sections;
- call `build_requirement_summary()`;
- call `build_optimizer_summary()`;
- call `build_dirty_state_summary()`;
- attach summaries and diagnostics to the JSON payload;
- keep existing `checks`, `issues`, `warnings`, and `status` behavior.

In `product_cli.py`:

- ensure local doctor failure prints structured diagnostics through existing
  `format_diagnostics_for_cli()` path;
- keep output wording product-neutral: `doctor completed` / `doctor failed`.

**Step 4: Run tests to verify pass**

Run:

```bash
./.venv/bin/python -m pytest tests/test_product_doctor.py tests/test_product_cli.py tests/test_doctor_readiness.py -q
```

Expected: PASS.

- [ ] Commit with message: `feat: extend local product doctor coverage`

## Task 5: Remote Doctor Uses Shared Summary Through Existing Cache

**Files:**

- Modify: `src/hermes_workflow/remote_doctor.py`
- Modify: `tests/test_remote_doctor.py`
- Modify: `tests/test_product_cli_remote.py`

**Step 1: Write remote parity tests**

Add tests with fake `RemoteSshRunner` and fake remote project files asserting:

```python
payload["transport"]["mode"] == "remote"
payload["transport"]["ssh_profile"] == "lab"
payload["requirement_summary"]["corner_count"] == 3
payload["evaluation_matrix"]["inside_candidate_execution"] == "serial"
payload["optimizer_summary"]["requested_strategy"] == "openbox_prf_eic"
```

Add a test that `parallel_jobs=24` creates `REMOTE_PARALLELISM_HIGH` warning
but does not fail doctor by itself.

**Step 2: Run tests to verify failure**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_doctor.py tests/test_product_cli_remote.py -q
```

Expected: FAIL because remote report lacks shared summaries.

**Step 3: Extend remote doctor without duplicating logic**

In `remote_doctor.py`:

- keep SSH login, remote directory, writable directory, remote cshrc, and remote
  `spectre/ocean` checks as transport-specific checks;
- use existing remote cache/prepare machinery where practical to create a local
  inspection project;
- run the same shared doctor readiness helper against the prepared local cache;
- merge shared diagnostics with remote transport diagnostics;
- write both remote and local report copies.

If using `prepare_remote_project_cache()` directly would run more than file
preparation, add a narrow helper in `remote_prepare.py` that prepares only files
needed for doctor. Do not create a second parser.

**Step 4: Run tests to verify pass**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_doctor.py tests/test_product_cli_remote.py tests/test_doctor_readiness.py -q
```

Expected: PASS.

- [ ] Commit with message: `feat: unify remote doctor feature coverage`

## Task 6: Product Documentation And Templates

**Files:**

- Modify: `README.md`
- Modify: `docs/USER_GUIDE_CN.md`
- Modify: `docs/TROUBLESHOOTING_CN.md`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_corner.md`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_tb_corner.md`
- Modify: `skills/ic-opt/SKILL.md`
- Modify: `src/hermes_workflow/agent_skills/ic-opt/SKILL.md`

**Step 1: Update docs to describe one doctor command**

Document:

```bash
ic-opt PROJECT --doctor
ic-opt --ssh-profile PROFILE PROJECT --doctor
```

Explain:

- local/remote are transport modes;
- doctor reports multi-corner matrix;
- doctor reports optimizer requested/resolved strategy;
- doctor reports budget precedence;
- doctor warns about dirty/incomplete run state;
- `parallel_jobs` is candidate-level concurrency.

**Step 2: Update examples/templates**

Ensure example requirements include current optimizer strategy options:

```yaml
optimizer:
  algorithm: openbox
  strategy: openbox_auto
```

For multi-corner templates, include `Process Corners` policy fields and a short
comment that model sections are user-provided.

**Step 3: Keep packaged and root agent skill in sync**

After editing `skills/ic-opt/SKILL.md`, copy the same content into:

```text
src/hermes_workflow/agent_skills/ic-opt/SKILL.md
```

**Step 4: Run docs/skill tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_agent_skill.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] Commit with message: `docs: explain unified doctor coverage`

## Task 7: Full Verification

**Files:**

- No implementation edits unless verification fails.

**Step 1: Run targeted tests**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/test_doctor_readiness.py \
  tests/test_product_doctor.py \
  tests/test_remote_doctor.py \
  tests/test_product_cli.py \
  tests/test_product_cli_remote.py \
  tests/test_agent_skill.py \
  tests/test_optimizer_strategy.py \
  tests/test_requirement_intake.py \
  -q
```

Expected: PASS.

**Step 2: Run full tests**

Run:

```bash
./.venv/bin/python -m pytest -q
```

Expected: PASS.

**Step 3: Run lint and cadence checks**

Run:

```bash
./.venv/bin/python -m ruff check src tests
./.venv/bin/python tools/check_development_cadence.py
git diff --cached --check -- . ':!vendor' ':!.serena'
```

Expected: all pass.

**Step 4: Optional product doctor smoke on real project directory**

Only after the user approves using the current real project directory, run doctor
without starting real optimization:

```bash
./.venv/bin/ic-opt /home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_3 --doctor
```

Expected:

- command does not start Spectre;
- report includes multi-corner and optimizer summaries;
- dirty-state warnings are visible if interrupted run artifacts remain.

- [ ] Commit with message: `test: verify unified doctor coverage`

## Completion Report Requirements

At the end of C-78 implementation, report:

- changed files;
- tests run and exact pass/fail status;
- whether any real project doctor smoke was run;
- whether dirty-state warnings were found in
  `/home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_3`;
- explicit statement that no Spectre/OCEAN optimizer run was started by doctor.
