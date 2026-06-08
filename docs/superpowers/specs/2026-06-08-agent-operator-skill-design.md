# Agent Operator Skill Design

Date: 2026-06-08

## Decision

IC Auto Opt Workflow is a deterministic optimization workflow tool for both
humans and AI agents. The agent-facing product route should not require a
two-agent handoff by default.

Default model:

```text
User -> current agent -> ic-opt CLI -> reports -> current agent explains result
```

Optional advanced model:

```text
User -> current agent -> same-runtime subagent -> ic-opt CLI -> current agent closeout
```

The optional subagent path is allowed only when the current runtime has a stable
native subagent/task mechanism and the user explicitly asks for it. It must not
be the default path.

## Product Goal

Make any supported agent runtime a reliable operator for `ic-opt`, not a
replacement optimizer. The agent should minimize user conversation and avoid
reconstructing information already present in `opt_requirement.md`.

## User Commands

Primary commands:

```text
/ic-opt PROJECT --doctor
/ic-opt PROJECT --real
/ic-opt PROJECT --continue M
```

If an agent surface does not support slash commands, the same behavior can be
triggered by a short natural-language request that includes the project path and
the intended mode.

## Default Agent Behavior

For `--doctor`, run:

```bash
ic-opt PROJECT --doctor
```

For `--real`, run:

```bash
ic-opt PROJECT --real
```

For `--continue M`, run:

```bash
ic-opt PROJECT --continue M
```

After a real or continuation run, read:

```text
PROJECT/reports/optimizer_decision_report.md
PROJECT/reports/optimizer_insight_report.md
```

Report:

- flow status;
- evaluation count and status counts;
- recommended run id and action;
- recommended parameters and metrics;
- bottleneck/warnings;
- whether the result is best observed only;
- next decision: accept, continue, revise constraints/FoM, or inspect failure.

## Agent Boundaries

The agent must not:

- hand-pick candidates;
- rewrite OCEAN formulas;
- parse PSF in Python;
- hardcode Spectre versions;
- create per-project Python virtualenvs;
- expose lower-level `hermes-workflow` commands to normal users unless debugging;
- poll every optimizer batch;
- recommend failed candidates as primary results when feasible candidates exist;
- claim a global optimum.

## Subagent Optional Mode

If a runtime-native subagent is explicitly requested and available, the current
agent may use it only for the execution stage. The supervisor remains
responsible for reading reports and explaining results.

If native subagent support is unavailable or denied, fall back to the default
single-agent CLI route only if the user agrees or the request did not require a
subagent.

## Files To Update

- `skills/ic-opt/SKILL.md`
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`

## Acceptance Criteria

- The default skill path tells agents to run `ic-opt` directly.
- Subagent wording is explicitly optional, not mandatory.
- `/ic-opt PROJECT --continue M` maps to the product CLI continuation command.
- The skill keeps all machine-critical content in `opt_requirement.md`.
- The skill tells agents to summarize reports, not invent optimization logic.
- Tests or static checks cover the updated text where practical.
