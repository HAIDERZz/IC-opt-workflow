# One-Command Optimizer Flow Design

Date: 2026-06-07
Status: Implemented as C-57 narrow MVP

## Purpose

Reduce production use to one short supervisor-agent request and one deterministic
Hermes command path. The user should put machine-critical data in
`opt_requirement.md`; the supervisor agent should not need a long operational
prompt to remember package, preflight, execution, closeout, and decision steps.

Target user interaction:

```text
Run the IC optimizer workflow for /home/zzchen/spectre_opt_prj/<project_name>.
```

Implemented CLI shape:

```bash
./.venv/bin/hermes-workflow optimize PROJECT_DIR --real \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10 \
  --cadence-cshrc /path/to/user/cadence_env.csh
```

The CLI command is a thin orchestration layer. It records
`reports/optimizer_flow_run_report.json` and stops before final user acceptance.

## Required Inputs

- `PROJECT_DIR/opt_requirement.md`
- Optional `PROJECT_DIR/constraints.md`
- User/project Cadence environment setup path, either in config generated from
  `opt_requirement.md` or passed explicitly to the command.

The command must not hardcode a Spectre version. Spectre selection comes from
the user environment.

## Required Flow

The one-command flow must wrap the existing proven steps:

1. `check-requirement`
2. `prepare-from-requirement`
3. `validate`
4. `check-project-ready`
5. `package`
6. `prepare-netlist`
7. `dry-run`
8. `preflight-health`
9. `approve`
10. `package-optimizer-task`
11. real optimizer execution from the approved task package
12. `check-optimizer-run`
13. `summarize-optimizer-run`
14. `finalize-optimizer-run`
15. `visualize-optimizer-run`
16. `decide-optimizer-run`
17. stop for user acceptance, unless explicit acceptance policy exists

## Supervisor / Execution-Agent Split

Supervisor agent:

- invokes the one-command flow or the current equivalent command sequence;
- reads final reports;
- explains best observed feasible candidate, bottleneck, feasibility counts, and
  whether continuation is justified;
- asks for user acceptance before recording a final decision unless the project
  defines an explicit acceptance policy.

Execution agent:

- runs only the approved real optimizer task package;
- does not hand-pick candidates;
- does not rewrite formulas;
- does not parse PSF;
- reports start, unexpected failure, completion, and low-frequency heartbeat
  status only for long runs.

## Decision Rule

The primary recommended run must be feasible when any feasible candidate exists.
Configured-objective ranking may still identify an infeasible mathematically
high-scoring point, but that point is diagnostic evidence, not an acceptance
target.

All recommendations remain `best observed`, not a global optimum certificate.

## Non-Goals

- No new optimizer backend.
- No new workflow engine.
- No chat-style intake parser.
- No speculative multi-project scheduler.
- No automatic user acceptance.

## Future Implementation Tasks

1. Done in C-57: add `hermes-workflow optimize PROJECT_DIR --real` as a thin orchestration
   command over the existing commands.
2. Done in C-57: add a generated `optimizer_flow_run_report.json` recording each subcommand,
   exit status, and key output paths.
3. Done in C-57: add a `--dry-orchestration` mode that verifies the sequence without launching
   real Spectre/OCEAN/OpenBox.
4. Future: add a short slash-command wrapper only after the CLI route is stable.
