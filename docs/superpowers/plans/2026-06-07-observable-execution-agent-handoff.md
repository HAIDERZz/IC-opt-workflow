# Observable Execution-Agent Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal observable supervisor-agent to independent execution-agent handoff mode for `/ic-opt PROJECT_DIR --real`.

**Architecture:** Preserve the existing direct automation path. Add one handoff module that launches Claude CLI as an execution-agent process after `package-optimizer-task`, captures transcript/report artifacts, and then lets the supervisor-side flow run closeout checks. The Claude `/ic-opt` skill opts into this mode by default.

**Tech Stack:** Python 3.11, Typer, subprocess, existing Hermes optimizer flow and task-package contracts, Claude CLI.

---

## Files

- Create `src/hermes_workflow/execution_agent_handoff.py`: launch and report the execution-agent process.
- Modify `src/hermes_workflow/optimizer_flow.py`: add `execution_agent` mode and call handoff at the existing `package-optimizer-task` boundary.
- Modify `src/hermes_workflow/product_cli.py`: expose `--execution-agent`.
- Modify `src/hermes_workflow/cli.py`: expose lower-level `hermes-workflow optimize --execution-agent`.
- Modify `claude_skills/ic-opt/SKILL.md`: append `--execution-agent claude` by default.
- Add tests in `tests/test_execution_agent_handoff.py`.
- Extend `tests/test_optimizer_flow.py` and `tests/test_product_cli.py`.

## Task 1: Handoff Report Writer

- [x] Add tests for report success/failure with a fake subprocess runner.
- [x] Implement `dispatch_execution_agent()`.
- [x] Verify transcript and JSON report paths are deterministic under `reports/`.

## Task 2: Optimizer Flow Wiring

- [x] Extend `OptimizerFlowReport` with `execution_agent` and optional `handoff_report_path`.
- [x] Add `execution_agent` to `optimize_project()`.
- [x] Preserve direct mode behavior.
- [x] In `claude` mode, replace only `run_openbox_real_optimization()` with `dispatch_execution_agent()`.
- [x] Keep supervisor-side `check-optimizer-run`, summarize, finalize, visualize, and decide steps after handoff.

## Task 3: CLI And Skill Wiring

- [x] Add `--execution-agent direct|claude` to `ic-opt`.
- [x] Add the same option to lower-level `hermes-workflow optimize`.
- [x] Update Claude `/ic-opt` skill so it appends `--execution-agent claude` unless the user already passed an execution-agent flag.
- [x] Keep shell `ic-opt` default as `direct`.

## Task 4: Verification And Real Handoff Drill

- [x] Run targeted tests for handoff, flow, product CLI, and skill-safe behavior.
- [x] Run cadence checker and diff whitespace checks.
- [x] Prepare a fresh real Mixer multi-testbench project with only `opt_requirement.md` and `cadence_env.csh`.
- [x] Run the real Claude CLI command:

```bash
claude -p --dangerously-skip-permissions "/ic-opt PROJECT_DIR --real"
```

- [x] Confirm `reports/execution_agent_handoff_report.json` has `status=pass`.
- [x] Confirm the optimizer run reached 100 real evaluations and wrote decision reports.
- [x] Sync progress docs and commit.

Evidence:

- `docs/CLAUDE_EXECUTION_AGENT_HANDOFF_2026-06-07.md`
- Fresh project:
  `/tmp/ic_auto_opt_c64_handoff_zX9JrO/Mixer_opt_muti_tb`
- Handoff report:
  `reports/execution_agent_handoff_report.json`, `status=pass`,
  `execution_agent=claude`, `returncode=0`
- Optimizer result: 100 real evaluations, `16 feasible`,
  `68 constraint_failed`, `16 metric_check_failed`, recommended feasible
  `real_051`, `global_optimum_claim=false`

## Self-Review

- Spec coverage: the plan covers the new handoff module, flow breakpoint,
  CLI/skill option, report artifacts, and real acceptance drill.
- Scope: no optimizer algorithm, OCEAN, Spectre, multi-testbench, or PSF logic
  changes are planned.
- Ambiguity: `direct` keeps current shell behavior; `claude` is the only new
  execution-agent mode.
