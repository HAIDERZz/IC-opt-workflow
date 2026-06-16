# C-78 Unified Doctor Feature Coverage Design
Date: 2026-06-13

## Current Bug Status

No blocking product-code bug is currently confirmed inside the verified contract
scope after the development/release sync checkpoint:

- full pytest passed in the development package;
- `ruff check src tests` passed;
- product-code staged whitespace check passed with `vendor/` and `.serena/`
  excluded;
- v0.1 tracked file coverage in the development package is now complete.

This does not mean the full optimizer has been real-tool validated. The known
remaining risks are feature coverage and observability gaps:

- local and remote doctor do not yet share one product-level readiness core;
- doctor does not yet summarize multi-corner evaluation matrix and policies;
- doctor does not yet report requested/resolved optimizer strategy, OpenBox
  surrogate/acquisition/acquisition-optimizer, or TuRBO mode;
- doctor does not yet make `max_evals`/config precedence visible to users;
- doctor does not yet clearly flag interrupted or dirty optimizer run state
  before a user starts another real run.

## Decision

C-78 completes the product doctor as a unified readiness/audit command for both
local and remote projects.

The product semantics remain:

```bash
ic-opt PROJECT --doctor
ic-opt --ssh-profile PROFILE PROJECT --doctor
```

The only local/remote difference is transport:

- local doctor reads and checks `PROJECT` directly;
- remote doctor uses SSH and the existing remote cache/prepare machinery to
  inspect the remote project, then runs the same shared requirement/config
  doctor core against the prepared local cache.

Remote doctor must not decide that an optimizer strategy is unsupported. The
optimizer controller remains local and receives a candidate adapter. Doctor only
reports transport readiness, requirement/config semantics, resolved optimizer
mode, resource settings, and dirty state.

## Goals

1. One shared doctor core for product semantics.
2. Local and remote doctor reports expose the same readiness sections.
3. Doctor covers C-76 multi-corner configuration.
4. Doctor covers C-77 optimizer strategy modes and effectiveness-audit inputs.
5. Doctor makes evaluation budget precedence visible.
6. Doctor warns about dirty/interrupted project state before real execution.
7. Existing CLI commands and report paths remain backward compatible.

## Non-Goals

- Do not run Spectre, OCEAN, Virtuoso, OpenBox, or TuRBO from doctor.
- Do not evaluate real metric formulas or parse PSF/waveform data.
- Do not rewrite OCEAN formulas, objective expressions, variable ranges, or
  process-corner definitions.
- Do not add a new `--local-doctor` or `--remote-doctor` command.
- Configure multi-corner coverage through `Process Corners` in `opt_requirement.md`.
- Do not change candidate/testbench/corner execution semantics.
- Do not create a Python virtualenv inside user project directories.
- Do not sync implementation changes into `ic-auto-opt-workflow-v0.1` until the
  development package has passed verification.

## Current Architecture

Current product entrypoint:

```text
src/hermes_workflow/product_cli.py
```

Current local doctor:

```text
src/hermes_workflow/product_doctor.py
```

Current remote doctor:

```text
src/hermes_workflow/remote_doctor.py
```

Current requirement semantic checks:

```text
src/hermes_workflow/requirement_semantics.py
src/hermes_workflow/requirement_intake.py
```

Current optimizer strategy and audit support:

```text
src/hermes_workflow/optimizer_strategy.py
src/hermes_workflow/optimizer_effectiveness.py
```

Current remote cache/transport support:

```text
src/hermes_workflow/remote_prepare.py
src/hermes_workflow/remote_project.py
src/hermes_workflow/remote_ssh.py
```

## Report Contract

Both local and remote doctor must write `reports/ic_opt_doctor_report.json`.

Local:

```text
PROJECT/reports/ic_opt_doctor_report.json
```

Remote:

```text
REMOTE_PROJECT/reports/ic_opt_doctor_report.json
~/.ic-opt/remote_runs/<profile>/<hash>/reports/ic_opt_doctor_report.json
```

The JSON report must preserve existing fields where present:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "checks": [],
  "issues": [],
  "warnings": [],
  "structured_issues": []
}
```

C-78 may add these fields:

```json
{
  "transport": {
    "mode": "local",
    "ssh_profile": null,
    "project_dir": "/path/to/project"
  },
  "requirement_summary": {
    "has_multi_testbench": true,
    "testbench_count": 2,
    "has_process_corners": true,
    "corner_count": 3,
    "objective_policy": "worst_case",
    "constraint_policy": "all_corners"
  },
  "evaluation_matrix": {
    "candidate_parallelism": 4,
    "testbench_count": 2,
    "corner_count": 3,
    "child_runs_per_candidate": 6,
    "inside_candidate_execution": "serial"
  },
  "optimizer_summary": {
    "algorithm": "openbox",
    "requested_strategy": "openbox_prf_eic",
    "resolved_backend": "openbox",
    "surrogate_type": "prf",
    "acq_type": "eic",
    "acq_optimizer_type": "local_random",
    "initial_trials": 22,
    "max_evaluations": 80,
    "max_evaluations_source": "config"
  },
  "resource_summary": {
    "parallel_jobs": 4,
    "threads_per_run": 8,
    "optimizer_cpu_threads": 4
  },
  "dirty_state": {
    "has_runs": true,
    "has_incomplete_real_run": false,
    "has_execution_package": true,
    "has_optimizer_state": true
  }
}
```

## Doctor Checks

### Shared Requirement And Config Checks

Doctor must use the existing requirement parser and generated config contract.

It must report:

- missing or invalid `opt_requirement.md`;
- requirement semantic issues from C-73;
- generated config validation failures;
- missing or invalid `constraints.md` when required;
- process-corner section presence;
- testbench count;
- corner count;
- process-corner objective and constraint policies;
- child-run matrix size per candidate.

### Multi-Corner Checks

Doctor must report multi-corner state without requiring real simulation:

- no `Process Corners` section means nominal single-corner behavior;
- one explicit corner means explicit single-corner behavior, not legacy downgrade;
- multiple corners means multi-corner behavior;
- `constraint_policy=all_corners` means constraints must pass on all required
  child runs;
- `objective_policy=worst_case` means doctor reports pessimistic aggregation
  but does not evaluate metrics.

Doctor must not guess PDK model section names. It only reports user-provided
corner ids, model sections, model files, and variables.

### Optimizer Checks

Doctor must report strategy resolution using the same resolver used by the real
optimizer flow:

- `openbox_auto`;
- `openbox_gp_eic`;
- `openbox_prf_eic`;
- `turbo_trust_region`;
- `random_baseline`.

Doctor must reject invalid user-facing names such as `openbox_eic` with the
same message family as the optimizer strategy resolver.

Doctor must display:

- requested strategy;
- resolved backend;
- resolved OpenBox surrogate type;
- resolved acquisition function;
- resolved acquisition optimizer;
- initial trials;
- max evaluations;
- max evaluations source.

`max_evaluations_source` values:

- `cli` when the caller explicitly passes a product-level override;
- `config` when generated `config/optimizer.yaml` supplies the value;
- `default` only if no requirement/config value exists and the code has to use a
  built-in fallback.

### Resource Checks

Doctor must summarize resource settings:

- `parallel_jobs`;
- `threads_per_run`;
- `optimizer_cpu_threads`.

Doctor must state that `parallel_jobs` is candidate-level concurrency. It must
not multiply concurrency by testbench count or corner count.

Remote doctor should warn when `parallel_jobs > 8` because remote SSH transport
can hit connection pressure. Local doctor should not warn on that threshold by
default.

### Dirty-State Checks

Doctor must detect and report potentially confusing project state:

- `runs/real/*` exists but lacks completion report;
- `state/optimizer_state.json` exists;
- `reports/optimizer_run_report.json` exists;
- `reports/optimizer_evaluations.jsonl` exists;
- `execution_package/` exists;
- continuation history is present.

Dirty state should not always fail doctor. It should warn unless the state is
internally inconsistent enough that starting a fresh real run is unsafe.

Examples:

- interrupted `runs/real/real_001` without expected report: warning with action
  to inspect or clean before fresh real run;
- optimizer history exists and user intends continuation: pass with summary;
- corrupt JSON in optimizer state: fail with structured issue.

## Transport Checks

### Local Transport

Local doctor checks:

- project path exists;
- `cadence_env.csh` resolution follows product discovery rules:
  `PROJECT/cadence_env.csh`, `IC_OPT_CADENCE_CSHRC`, `~/.ic-opt/cadence_env.csh`,
  or explicit `--cadence-cshrc`;
- local Cadence cshrc file exists;
- `check_toolchain_environment()` verifies required tool availability where
  supported.

### Remote Transport

Remote doctor checks:

- SSH login works;
- remote project directory exists;
- remote project directory is writable;
- remote requirement files can be read;
- remote Cadence cshrc exists;
- remote `spectre` and `ocean` resolve after sourcing cshrc;
- remote project can be prepared into local cache using existing remote prepare
  machinery;
- shared doctor core runs against the prepared local cache.

Remote doctor must write both remote and local report copies.

## CLI Behavior

For both local and remote:

- pass prints `doctor completed`;
- fail prints `doctor failed`;
- structured diagnostics are printed before plain legacy issues;
- exit code is `0` on pass and `1` on fail.

The CLI should avoid user-visible language that makes local and remote look like
two different products. It can say `transport: local` or `transport: remote`.

## Acceptance Criteria

1. `ic-opt PROJECT --doctor` writes a report with transport, requirement,
   matrix, optimizer, resource, and dirty-state summaries.
2. `ic-opt --ssh-profile PROFILE PROJECT --doctor` writes the same semantic
   summaries plus SSH/toolchain transport checks.
3. Remote doctor uses existing remote prepare/cache/tooling instead of creating
   a parallel requirement parser.
4. Doctor reports multi-corner policy and child runs per candidate.
5. Doctor reports optimizer requested/resolved strategy and OpenBox/TuRBO
   details.
6. Doctor reports `max_evaluations_source`.
7. Doctor warns on remote `parallel_jobs > 8`.
8. Doctor detects interrupted or dirty run state.
9. Existing product CLI, lower-level CLI, and report consumers remain backward
   compatible.
10. Full unit tests, ruff, cadence check, and product-code whitespace check pass
    in `ic-auto-opt-workflow`.
