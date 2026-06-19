# Handoff To Linux Codex

This document transfers the current IC auto-optimization workflow design from the Windows exploration workspace to the Linux implementation workspace.

## 1. Current Status

The project is still in architecture and planning stage. No production workflow code has been implemented yet.

The current source of truth is:

- `PROJECT_STRUCTURE.md`
- this handoff document

The existing `virtuoso-bridge-lite` project must remain a dependency and reference implementation. Do not reimplement its `virtuoso`, `spectre`, or `optimizer` skills.

## 2. Target Linux Workspace Layout

Use this sibling-directory layout on the Linux server:

```text
/workspace/eda-ai-agent/
  virtuoso-bridge-lite/
  ic-auto-opt-workflow/
```

`ic-auto-opt-workflow` is the upper workflow layer. `virtuoso-bridge-lite` is the lower tool/skill layer.

## 3. Core Consensus

The first MVP uses a Maestro-exported Spectre deck backend.

The user already creates and validates the testbench in Virtuoso/Maestro. The user should provide the testbench locator, variable list, metric formulas, hard constraints, objective, and optimizer/simulation budget. The user does not need to manually describe the full simulation setup such as `tran`, `dc`, `sp`, `pss`, model includes, save options, or simulator options.

Claude Code uses the `virtuoso` skill from `virtuoso-bridge-lite` to read the actual Maestro setup and export a Spectre deck with `maeCreateNetlistForCorner`. The exported `input.scs` is the source of truth for simulation setup.

Claude Code must not modify simulation setup. It may only template user-approved optimization variables.

The optimization loop should run standalone Spectre through the `spectre` skill, then use the `optimizer` skill for candidate generation and search.

## 4. Agent Roles

Hermes is the supervisor agent.

Hermes responsibilities:

- interact with the user
- parse user optimization requests
- generate project config and metric contract
- maintain project-level Markdown files
- validate completeness of variables, metrics, constraints, objective, Spectre settings, and optimizer settings
- create the execution package for Claude Code
- approve or reject the first real execution after dry run and review
- read structured state/report files
- handle escalation
- generate final summary and final report

Hermes must not directly run Virtuoso, Spectre, or optimizer skills.

Claude Code is the execution agent.

Claude Code responsibilities:

- use `virtuoso`, `spectre`, and `optimizer` skills from `virtuoso-bridge-lite`
- export and inspect the real Maestro-generated Spectre deck
- template only approved variables
- implement project-local `metrics.py` from the metric contract
- run mandatory dry run and self-review
- wait for Hermes approval before first real Spectre/optimizer execution
- run the full optimization loop after approval
- write ledger, state, health, report, and escalation files

Claude Code must not change hard constraints, objective, variable ranges, or Hermes project rules.

## 5. Metric Contract Decision

For MVP, the user must provide metric formulas.

Hermes extracts these formulas into a metric contract. Claude Code uses the contract to implement `metrics.py` for the specific project.

Do not build a generic Maestro calculator formula parser in the first version. That can be a later Python API/library project.

## 6. Safety Gates

The first generated simulation/runner/metric scripts require:

- Claude Code self-review
- dry run
- Hermes approval

Dry run must include:

- parse configs
- validate variables, metrics, constraints, and objective
- render one candidate netlist
- verify all placeholders are replaced
- import `metrics.py`
- run metrics with mock `SimulationResult`
- evaluate constraints and objective
- test ledger/state writes
- write `dry_run_report.json`
- write `review_report.md`

After approval, optimizer batches can continue automatically if no script, setup, metric contract, objective, constraint, or variable-range changes occur.

Any such change requires escalation back to Hermes.

## 7. Agent Verification Strategy

Before full Hermes-Claude integration, verify each agent independently through file contracts.

Verify Claude Code with Codex acting as Hermes:

```text
Codex/Hermes-stub
  -> creates execution_package
  -> invokes Claude Code
  -> inspects Claude output files
```

Expected Claude outputs include:

- `reports/netlist_preparation_report.json`
- `reports/dry_run_report.json`
- `reports/review_report.md`
- `state/health_check.json`
- `state/best_candidate.json`
- `state/optimizer_state.json`
- `ledger/experiment_ledger.jsonl`
- `escalation_report.json` when abnormal

Verify Hermes with Codex acting as Claude:

```text
Codex/Claude-stub
  -> receives Hermes project config and execution package
  -> writes simulated reports/state/escalation
  -> checks Hermes supervisor_instruction/final_report behavior
```

Only after both single-agent checks pass should Hermes and Claude be connected through Hermes' native `Claude-cli-skill`.

## 8. Important Open Interface

The exact interface of Hermes' native `Claude-cli-skill` is not confirmed yet.

Before implementation, confirm:

- how Hermes passes `execution_package` path to Claude Code
- how Hermes constrains Claude Code to use required skills
- how Claude Code pauses for Hermes approval
- how Hermes reads Claude-generated reports/state files
- how immutable contract files are protected

Do not design the workflow around chat history. The project state must be persisted in files.

## 9. Files To Read First On Linux

In the new Linux Codex session, read these first:

```text
ic-auto-opt-workflow/PROJECT_STRUCTURE.md
ic-auto-opt-workflow/docs/HANDOFF_TO_LINUX_CODEX.md
virtuoso-bridge-lite/README.md
virtuoso-bridge-lite/AGENTS.md
virtuoso-bridge-lite/skills/virtuoso/SKILL.md
virtuoso-bridge-lite/skills/spectre/SKILL.md
virtuoso-bridge-lite/skills/optimizer/SKILL.md
```

Suggested first instruction for Linux Codex:

```text
Please read the handoff and project structure docs first. Then continue by creating the execution plan for the IC auto-optimization workflow on top of virtuoso-bridge-lite. Do not implement code until the plan is approved.
```

## 10. Next Recommended Work

The next step is to create an implementation plan, not to implement the full system immediately.

Recommended planning phases:

1. File contract and schema definition
2. Hermes project template generation
3. Hermes validation and execution package builder
4. Claude-side dry-run package expectations
5. Agent verification harnesses
6. Mock simulator optimization loop
7. Exported `input.scs` optimization loop
8. Real Linux Virtuoso/Spectre integration

