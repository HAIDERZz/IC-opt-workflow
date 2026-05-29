# Opencode Handoff 2026-05-29

This handoff summarizes the current `ic-auto-opt-workflow` state so opencode can continue development without replaying completed Plan A work.

## Repository State

- Repo: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`
- Branch: `plan-a-hermes-file-contract-mvp`
- Focused plan: `docs/superpowers/plans/2026-05-28-hermes-file-contract-mvp.md`
- Historical planning context: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Latest implementation commit before handoff docs: `720adb9 fix: clarify cli json error handling`

## Current Status

Focused Plan A, Hermes File Contract MVP, is complete through Task 9.

Completed scope:

- Python package scaffold and Typer entry point.
- Pydantic schemas for the five structured YAML contracts.
- Cross-file validation for config, variables, metrics, Spectre policy, optimizer budget, and objective references.
- Packaged Spectre Maestro project template using `importlib.resources`.
- Execution package manifest with immutable config hashes.
- `EXECUTION_TASK.md` renderer.
- Claude preflight report readers.
- Hermes first-run approval gate writing `supervisor_instruction.json`.
- MVP CLI commands: `init`, `validate`, `package`, `approve`.
- CLI smoke tests and traceback-free domain-error tests.
- Project-local Claude Review MCP server for spec and code-quality gates.

Out of scope and not implemented:

- `USER_TASK.md` parser.
- Claude CLI workflow invocation for real execution.
- Virtuoso bridge startup or Maestro netlist export.
- Spectre simulation.
- Optimizer or TuRBO loop execution.
- Project-local runner files such as `render_netlist.py`, `dry_run.py`, `run_candidate.py`, or `optimization_loop.py`.
- Final optimization report generation.

## Verification And Reviews

Latest verification before this handoff:

```bash
pytest -q
# 56 passed

ruff check .
# All checks passed
```

Task 9 review gates at final code head:

- Spec review: compliant with noted defensive extras.
- Code-quality review: no Critical or Important issues.

Review tooling:

- MCP server script: `tools/claude_review_mcp.py`
- Project MCP config: `.mcp.json`
- Documentation: `docs/CLAUDE_REVIEW_MCP.md`

`spec_review` arguments:

- `repo_path`
- `task_text`
- `implementer_report`
- optional `git_range`
- optional `extra_context`

`code_quality_review` arguments:

- `repo_path`
- `requirements`
- `base_sha`
- `head_sha`
- `description`
- optional `extra_context`

The MCP server shells out to `claude -p` in plan mode. Network latency can be high; avoid launching duplicate review calls while one is running.

## Files To Read First

Read in this order:

```text
docs/OPENCODE_HANDOFF_2026-05-29.md
docs/EXECUTION_PROGRESS_2026-05-29.md
docs/COMPACT_RESUME_CHECKPOINT.md
docs/superpowers/plans/2026-05-28-hermes-file-contract-mvp.md
docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md
README.md
```

For implementation details, inspect:

```text
src/hermes_workflow/schemas.py
src/hermes_workflow/validate.py
src/hermes_workflow/package.py
src/hermes_workflow/reports.py
src/hermes_workflow/approvals.py
src/hermes_workflow/cli.py
tests/
```

## Next Development Decision

Focused Hermes Plan A ends at Task 9. There is no Task 10 in this Hermes File Contract MVP plan.

Recommended next move for opencode:

1. Treat Plan A Task 1-9 as complete.
2. Do not rework completed modules unless a new review finding appears.
3. Ask the user to confirm the next development scope.
4. For any follow-up scope, write or refresh a focused plan first, then implement with TDD and run spec/code-quality review gates before moving on.

## One-Sentence Continue Prompt

```text
请在 /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow 的 branch plan-a-hermes-file-contract-mvp 上继续开发：先阅读 docs/OPENCODE_HANDOFF_2026-05-29.md、docs/EXECUTION_PROGRESS_2026-05-29.md、docs/COMPACT_RESUME_CHECKPOINT.md 和 Hermes Plan A 文件；Hermes File Contract MVP 的 Plan A Task 1-9 已完成并通过 review/pytest/ruff，不要重做，也不要寻找 Plan A Task 10；下一步先向用户确认新的后续开发范围，并为该范围新建或刷新 scoped plan。
```
