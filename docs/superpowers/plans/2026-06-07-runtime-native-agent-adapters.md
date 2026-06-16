# C-65 Runtime-Native Agent Adapters

Date: 2026-06-07

## Goal

Make the product landing path match the intended agent UX:

```text
User -> current runtime supervisor agent -> same-runtime execution subagent
```

The shell command `ic-opt PROJECT_DIR --real` remains the deterministic
automation core and direct operator/debug route. C-64's `--execution-agent
claude` subprocess handoff remains development evidence, not the C-65 default
product target.

## Scope

- Add runtime adapter assets for Claude and OpenCode.
- Add a small repo-local installer/status command for those assets.
- Update product docs so runtime-native same-CLI subagent delegation is the
  target model.
- Write a beginner-friendly Chinese guide for IC users.
- Validate assets with targeted tests and runtime CLI smoke checks where the
  local environment allows.

## Non-Goals

- No optimizer algorithm changes.
- No new fake optimizer ladder.
- No Spectre/OCEAN formula changes.
- No PSF parsing.
- No cross-CLI default execution-agent model.
- No Codex/OpenClaw/HermesAgent adapter in this task.

## Tasks

- [x] Task 1: Claude/OpenCode runtime adapter assets.
- [x] Task 2: `hermes-workflow install-runtime-adapter` and
  `runtime-adapter-status`.
- [x] Task 3: product documentation/status synchronization.
- [x] Task 4: beginner-friendly Chinese user quickstart.
- [x] Task 5: verification and runtime CLI smoke evidence.

## Route Audit

- Active spec: this narrow C-65 plan.
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`.
- Alignment: preserves the role model by keeping Hermes as deterministic
  tooling, the current runtime as supervisor, and the same runtime's subagent as
  execution agent.
- Drift: reclassifies C-64 `--execution-agent claude` as development evidence
  instead of final product default. No optimizer or real-tool contract changed.
