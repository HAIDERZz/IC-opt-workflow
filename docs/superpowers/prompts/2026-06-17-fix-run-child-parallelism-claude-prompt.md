# Claude Development Prompt: Fix-Run Child Parallelism

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is the development package. The release package is:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1
```

Do not edit the release package unless the user explicitly asks for a release
sync after dev verification.

## Required Context

Read these files first:

```text
AGENTS.md
docs/superpowers/specs/2026-06-17-fix-run-child-parallelism-design.md
docs/superpowers/plans/2026-06-17-fix-run-child-parallelism.md
src/hermes_workflow/fix_run_flow.py
src/hermes_workflow/remote_fix_run_flow.py
tests/test_fix_run_flow.py
tests/test_remote_fix_run_flow.py
```

Use `rtk` before shell commands.

The dev worktree may already contain unrelated dirty changes from prior
fix-run/release work. Do not revert or rewrite them. Stage only files you
modify for this task if you commit.

## Goal

Implement bounded child-level parallelism for fix-run:

- Use `Spectre Settings.parallel_jobs` as max concurrent child
  `testbench x corner` Spectre/OCEAN adapter runs.
- Keep `threads_per_run` as per Spectre process.
- Keep fixed points serial.
- Keep local and remote artifact/report contracts unchanged.
- Do not add a new CLI flag.

## Implementation Plan

Follow:

```text
docs/superpowers/plans/2026-06-17-fix-run-child-parallelism.md
```

Implement task-by-task with TDD:

1. Add failing local concurrency tests.
2. Implement local child scheduler.
3. Add failing remote concurrency tests.
4. Implement remote child scheduler.
5. Add failure preservation regression tests.
6. Update dev docs.
7. Run final verification.

## Important Design Constraints

- Do not parallelize fixed points in this first implementation.
- Do not mutate shared report lists from worker threads.
- Worker threads should return child outcomes; the main thread should update
  `child_issues`, `scalar_metric_manifest_paths`, and final report data.
- Preserve deterministic child order in report path collection.
- A child adapter exception should become `ChildRunIssue`, not abort the whole
  fixed point.
- If any child fails, parent `reports/fix_run_report.json` should fail.
- Remote report sync remains after all children complete.
- No real Spectre/OCEAN/SSH run is required for unit tests.

## Verification Commands

Run these from the dev package root:

```bash
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_fix_run_flow.py tests/test_remote_fix_run_flow.py tests/test_product_cli.py tests/test_validate.py -q
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest -q
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests
rtk git diff --check
```

## Required Final Report

When finished, report:

- files changed
- commits made, if any
- focused test result
- full test result
- ruff result
- diff-check result
- whether release sync is still pending

Do not claim success without fresh verification output.
