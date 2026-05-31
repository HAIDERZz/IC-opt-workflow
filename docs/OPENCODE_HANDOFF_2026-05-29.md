# Opencode Handoff 2026-05-29 (updated 2026-05-31 after C-3 completion)

This handoff was originally dated 2026-05-29 and updated 2026-05-31 after C-3 final verification. It summarizes the current `ic-auto-opt-workflow` state so opencode can continue development without replaying completed work.

## Repository State

- Repo: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`
- Branch: `plan-a-hermes-file-contract-mvp`
- Focused plan: `docs/superpowers/plans/2026-05-28-hermes-file-contract-mvp.md`
- Historical planning context: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Latest next-development log: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Latest C-3 code commit before docs-only handoff cleanup: `edb107f fix: harden preflight readiness gates`; later docs commits may exist through current HEAD

## Current Status

Plan A (Hermes File Contract MVP) Task 1-9 complete. Plan B (mock optimization loop) complete. Plan C-1 (netlist template contract) complete. Plan C-2 (dry-run candidate renderer) complete. Plan C-3 (execution package preflight readiness) complete and reviewed as of 2026-05-31.

Plan A completed scope:

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

Latest verification for C-3 closeout:

```bash
pytest -q
# 173 passed

ruff check .
# All checks passed
```

C-3 final review gates:

- Final spec review: no Critical or Important findings.
- Final code-quality review: no Critical or Important findings after `edb107f`.

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
docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md
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
src/hermes_workflow/health.py              # preflight health-check report writer
src/hermes_workflow/netlists.py             # Spectre netlist parameter templater
src/hermes_workflow/cli.py
tests/
```

## Next Development Decision

Plan A Task 1-9, Plan B, Plan C-1, Plan C-2, and Plan C-3 are complete and reviewed.

Recommended next move for opencode:

1. Treat Plan A Task 1-9, Plan B, Plan C-1, Plan C-2, and Plan C-3 as complete.
2. Do not rework completed modules unless a new review finding appears.
3. Confirm the next Plan C development scope before starting implementation.
4. Real `input.scs` examples under `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example` are local reference material only and must not be committed.
5. Preflight-health state is tracked in `state/health_check.json` (see `src/hermes_workflow/health.py` and `hermes-workflow preflight-health` CLI).

## One-Sentence Continue Prompt

```text
请在 /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow 的 branch plan-a-hermes-file-contract-mvp 上继续开发：先阅读 docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md、docs/OPENCODE_HANDOFF_2026-05-29.md、docs/EXECUTION_PROGRESS_2026-05-29.md、docs/COMPACT_RESUME_CHECKPOINT.md 和 Hermes Plan A 文件。Plan A Task 1-9、Plan B、Plan C-1、Plan C-2、Plan C-3 均已完成并通过 review gate；C-3 最终验证为 pytest -q 173 passed、ruff clean、final spec/code-quality review 无 Critical/Important。下一步先确认新的 Plan C 范围并写 scoped plan。本地 input.scs 示例禁止提交到仓库。
```
