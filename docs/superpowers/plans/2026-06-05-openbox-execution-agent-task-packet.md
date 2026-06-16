# OpenBox Execution-Agent Task Packet Implementation Plan

> **For agentic workers:** Use a lightweight subagent-driven cadence when it
> materially helps. Keep this scope narrow: task packet rendering, CLI wiring,
> tests, and state docs only.

**Goal:** Add an explicit OpenBox variant to the optimizer execution-agent task
packet so execution agents can run the C-29 backend without guessing commands or
audit requirements.

**Architecture:** Extend the existing `optimizer_task_package.py` renderer and
`package-optimizer-task` CLI. Preserve native TuRBO as the default.

**Tech Stack:** Python, Typer, pytest, ruff.

## Boundaries

- Do not run real Virtuoso/Spectre/OCEAN.
- Do not replace TuRBO or make OpenBox the global default.
- Do not add optimizer algorithm behavior.
- Do not parse PSF.
- Do not rewrite OCEAN formulas.
- Do not add broad orchestration assets.

## File Map

- Modify: `src/hermes_workflow/optimizer_task_package.py`
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_optimizer_task_package.py`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`

## Task 1: Backend-Aware Package Contract

- [x] Add an `optimizer_backend` argument to
  `build_optimizer_execution_task_package`, defaulting to `native_turbo`.
- [x] Add backend validation for `native_turbo` and `openbox`.
- [x] Add manifest fields for `backend` and `audit_commands`.
- [x] Preserve existing native command shape by default.

Verify:

```bash
python3 -m pytest tests/test_optimizer_task_package.py::test_build_optimizer_execution_task_package_writes_task_and_manifest -q
```

## Task 2: OpenBox Task Rendering

- [x] Render `run-openbox-real` command for `optimizer_backend="openbox"`.
- [x] Include OpenBox dependency-blocker wording.
- [x] Include explicit no-silent-fallback wording.
- [x] Include post-run `check-optimizer-run` and `summarize-optimizer-run`
  commands.
- [x] Ensure forbidden actions stay in the forbidden section.

Verify:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
```

## Task 3: CLI Wiring

- [x] Add `--backend native-turbo|openbox` to `package-optimizer-task`.
- [x] Keep the default backend as native TuRBO.
- [x] Add CLI coverage for OpenBox package generation.

Verify:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
python3 -m ruff check src/hermes_workflow/optimizer_task_package.py src/hermes_workflow/cli.py tests/test_optimizer_task_package.py
```

## Task 4: Final Verification And State Sync

- [x] Run focused regression.
- [x] Update state and progress docs.
- [x] Commit the C-30 scope.

Verify:

```bash
python3 -m pytest tests/test_optimizer_task_package.py tests/test_openbox_backend.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py -q
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-openbox-execution-agent-task-packet-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment:
  C-30 keeps the workflow as a lightweight agent handoff layer and makes the
  proven OpenBox backend executable by an agent without manual interpretation.
- Drift:
  None planned. TuRBO remains implemented and default.
