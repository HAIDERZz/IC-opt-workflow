# Optimizer Execution-Agent Task Packet MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a standard Hermes optimizer execution-agent task packet for the proven `run-native-turbo --parallel` real-tool acceptance flow.

**Architecture:** Keep the existing optimizer runner as the only execution path. Hermes generates a small task markdown file plus manifest under `execution_package/`, naming the exact command, Spectre/OCEAN settings to audit, returned artifacts, and forbidden actions learned from C-19/C-20. The execution agent still runs real tools; Hermes still audits manifests after return.

**Tech Stack:** Existing `hermes-workflow` CLI, Typer, `package.py` patterns, `run-native-turbo`, pytest, ruff.

---

## Scope Guard

Allowed:

- generate one optimizer execution-agent task packet from existing project config;
- include the existing `run-native-turbo PROJECT_DIR --parallel --max-evals N --cadence-cshrc PATH` command;
- include C-20 manifest-level audit rules;
- include Spectre settings audit expectations: `preset`, `threads_per_run`, `parallel_jobs`, and `output_format`;
- include required returned artifacts already produced by the existing runner.

Forbidden:

- add a new optimizer algorithm;
- add a daemon, scheduler, database, service, or broad framework;
- run Virtuoso, Spectre, OCEAN, SSH, `virtuoso-bridge-lite`, or real execution agents in this plan;
- parse PSF in Python;
- rewrite OCEAN formulas;
- flatten or replace the native Maestro/ADE netlist layout;
- commit raw Cadence artifacts.

## File Plan

- Create: `src/hermes_workflow/optimizer_task_package.py`
  - Small renderer/writer for optimizer execution task text and manifest.
- Modify: `src/hermes_workflow/cli.py`
  - Add a CLI command that delegates to the renderer/writer.
- Create: `tests/test_optimizer_task_package.py`
  - Focused rendering and CLI tests using temporary fixture projects.
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify as needed: this plan file.

## Task 1: Renderer And Manifest Contract

**Risk:** Medium. File-writing contract, but no real tools.

**Status:** Complete, verified-only.

**Files:**

- Create: `src/hermes_workflow/optimizer_task_package.py`
- Create: `tests/test_optimizer_task_package.py`

- [x] **Step 1: Write failing renderer test**

Add a test that initializes the fixture project, calls the new writer, and asserts:

```python
assert task_path.name == "OPTIMIZER_EXECUTION_TASK.md"
assert manifest_path.name == "optimizer_execution_manifest.json"
assert "run-native-turbo" in task_text
assert "--parallel" in task_text
assert "--max-evals 100" in task_text
assert "Command exit status alone is not acceptance evidence" in task_text
assert "Manifest-level audit is required" in task_text
assert "threads_per_run" in task_text
assert "parallel_jobs" in task_text
assert "ledger/experiment_ledger.jsonl" in task_text
```

Run:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
```

Expected: fails because the module does not exist.

- [x] **Step 2: Implement minimal writer**

Add:

```python
build_optimizer_execution_task_package(
    project_dir: Path,
    *,
    max_evals: int,
    cadence_cshrc: Path,
    parallel: bool = True,
    created_at_utc: str | None = None,
) -> OptimizerExecutionTaskPackage
```

Write:

```text
execution_package/OPTIMIZER_EXECUTION_TASK.md
execution_package/optimizer_execution_manifest.json
```

The manifest must include:

- `schema_version`
- `created_at_utc`
- `project_dir`
- `command`
- `max_evals`
- `parallel`
- `cadence_cshrc`
- `spectre_settings`
- `required_returned_artifacts`

Required returned artifacts match the existing native runner constants
`REPORT_RELATIVE` and `EVALUATIONS_RELATIVE`:

```text
reports/native_turbo_optimizer_report.json
reports/native_turbo_optimizer_evaluations.jsonl
state/optimizer_state.json
ledger/experiment_ledger.jsonl
```

- [x] **Step 3: Verify focused test passes**

Run:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
python3 -m ruff check src/hermes_workflow/optimizer_task_package.py tests/test_optimizer_task_package.py
```

Expected: pass.

## Task 2: CLI Wiring

**Risk:** Medium. CLI integration, no real tools.

**Status:** Complete, verified-only.

**Files:**

- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_optimizer_task_package.py`

- [x] **Step 1: Write failing CLI test**

Add a Typer runner test for:

```bash
hermes-workflow package-optimizer-task PROJECT_DIR --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh --parallel
```

Assert:

```python
assert result.exit_code == 0
assert "execution_package/OPTIMIZER_EXECUTION_TASK.md" in result.stdout
assert (project_dir / "execution_package/OPTIMIZER_EXECUTION_TASK.md").exists()
assert (project_dir / "execution_package/optimizer_execution_manifest.json").exists()
```

Run:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
```

Expected: fails because the CLI command does not exist.

- [x] **Step 2: Add CLI command**

Add `package-optimizer-task` to `src/hermes_workflow/cli.py`. The command must only write the package and print relative paths. It must not run real tools.

- [x] **Step 3: Verify CLI test passes**

Run:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
python3 -m ruff check src/hermes_workflow/cli.py src/hermes_workflow/optimizer_task_package.py tests/test_optimizer_task_package.py
```

Expected: pass.

## Task 3: Local Fake Handoff Smoke

**Risk:** Low. Local-only packet inspection.

**Files:**

- Modify: `tests/test_optimizer_task_package.py`
- Modify: this plan file
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

- [ ] **Step 1: Add smoke test**

Add a test that reads the generated task packet and confirms it does not mention:

```text
Claude Code
hand-pick
parse PSF
rewrite OCEAN
```

The first two must be absent. The last two should appear only as forbidden actions.

- [ ] **Step 2: Verify focused and adjacent tests**

Run:

```bash
python3 -m pytest tests/test_optimizer_task_package.py tests/test_package.py tests/test_native_turbo.py -q
python3 -m ruff check src/hermes_workflow/cli.py src/hermes_workflow/optimizer_task_package.py tests/test_optimizer_task_package.py
python3 tools/check_development_cadence.py
git diff --check
```

Expected: pass.

## Task 4: Final Review And Commit

**Risk:** Low-to-medium. No real tools.

**Files:**

- Modify: this plan file
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify as needed by Lean Evidence Gate: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify as needed by Lean Evidence Gate: `docs/COMPACT_RESUME_CHECKPOINT.md`

- [ ] **Step 1: Run final verification**

Run:

```bash
python3 -m pytest tests/test_optimizer_task_package.py tests/test_package.py tests/test_native_turbo.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

Expected: pass.

- [ ] **Step 2: Record route audit**

Record:

```text
Active plan: docs/superpowers/plans/2026-06-04-optimizer-execution-agent-task-packet.md
Top-level plan: docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md
Alignment: C-23 productizes the proven C-19/C-20 handoff packet without changing the optimizer runner.
Drift: none. No real tools, new optimizer algorithm, PSF parser, OCEAN formula rewrite, or layout replacement.
```

- [ ] **Step 3: Commit**

Use explicit pathspecs:

```bash
git add src/hermes_workflow/optimizer_task_package.py src/hermes_workflow/cli.py tests/test_optimizer_task_package.py docs/superpowers/plans/2026-06-04-optimizer-execution-agent-task-packet.md docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/COMPACT_RESUME_CHECKPOINT.md
git commit -m "feat: package optimizer execution task"
```

Do not stage raw Cadence evidence or `/tmp` files.

## Self-Review

- Spec coverage: The plan turns the proven C-19/C-20 hand-written task packet into a generated Hermes packet and keeps `run-native-turbo --parallel` as the execution path.
- Boundary check: The plan does not run real tools and does not add optimizer framework code.
- Placeholder scan: No placeholder markers remain.
- Next after C-23: run one local worker-agent handoff using the generated packet, only after user confirmation.
