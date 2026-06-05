# C-38 OpenBox Continuation / Multi-Run Optimizer Workflow Implementation Plan

Date: 2026-06-05

Design spec:

```text
docs/superpowers/specs/2026-06-05-openbox-continuation-multi-run-workflow-design.md
```

## Route Audit

- Active spec: `docs/superpowers/specs/2026-06-05-openbox-continuation-multi-run-workflow-design.md`
- Top-level plan: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: Extends the accepted OpenBox optimizer execution-agent route with
  a continuation command and packet. It preserves existing Spectre/OCEAN,
  metric, result, ledger, and acceptance contracts.
- Drift: None intended. No real-tool run is part of this implementation plan.

## Task 1: Continuation Trace Loading And Warm-Start Tests

- [x] Add failing tests proving:
  - continuation loads prior backend-neutral OpenBox traces;
  - prior traces are converted to advisor observations before new suggestions;
  - prior parameter tuples seed duplicate detection;
  - cumulative reports keep prior plus new traces.
- [x] Implement the smallest helper layer needed inside `openbox_backend.py`.
- [x] Keep existing non-continuation behavior unchanged.

Verification:

```bash
python3 -m pytest tests/test_openbox_backend.py -q
```

## Task 2: CLI Continuation Command

- [x] Add `hermes-workflow continue-openbox-real PROJECT_DIR
  --additional-evals N`.
- [x] Reuse the same batch-size, parallel-jobs, cadence-cshrc, and dependency
  semantics as `run-openbox-real`.
- [x] Add a focused CLI test.

Verification:

```bash
python3 -m pytest tests/test_openbox_backend.py -q
python3 -m ruff check src/hermes_workflow/openbox_backend.py src/hermes_workflow/cli.py tests/test_openbox_backend.py
```

## Task 3: Execution-Agent Continuation Packet

- [x] Extend `package-optimizer-task` with a narrow continuation option for the
  OpenBox backend.
- [x] Render `continue-openbox-real` and `--additional-evals` in the generated
  task and manifest.
- [x] Keep native TuRBO and OpenBox first-run packet behavior unchanged.

Verification:

```bash
python3 -m pytest tests/test_optimizer_task_package.py -q
python3 -m ruff check src/hermes_workflow/optimizer_task_package.py src/hermes_workflow/cli.py tests/test_optimizer_task_package.py
```

## Task 4: Final Verification And State Sync

- [x] Run focused continuation tests.
- [x] Run optimizer-adjacent tests.
- [x] Run cadence checker and whitespace check.
- [x] Update `docs/CURRENT_TASK_STATE.json`, `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`,
  and this plan.

Verification:

```bash
python3 -m pytest tests/test_openbox_backend.py tests/test_optimizer_task_package.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
```
