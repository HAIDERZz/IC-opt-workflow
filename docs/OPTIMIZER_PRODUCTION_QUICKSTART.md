# Optimizer Production Quickstart

This is the shortest supported path for using `ic-auto-opt-workflow` on a real
Maestro-exported Spectre/OCEAN optimization project.

For a user-facing manual that explains how to ask a supervisor agent to run the
workflow, read `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`. For the current
implemented agent boundary, read `docs/AGENT_INTEGRATION_STATUS.md`; for the
detailed Chinese status explanation, read
`docs/PROJECT_STATUS_AND_ARCHITECTURE_CN.md`.

The workflow is file based. Do not describe machine-critical setup only in
chat. Put the request in `opt_requirement.md`, optionally put human guidance in
`constraints.md`, then let Hermes generate and check the contracts.

## 0. Product Environment Model

Use one product-level Python virtualenv for the `ic-auto-opt-workflow`
installation and optimizer dependencies. Do not create a separate virtualenv
inside every user project.

From the repository root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Implemented shell product invocation:

```bash
ic-opt ~/spectre_opt_prj/<project_name> --real
```

Target supervisor-agent invocation, not yet implemented as a real slash command:

```text
/ic-opt ~/spectre_opt_prj/<project_name> --real
```

The current project does not yet provide a Codex/Claude slash-command wrapper
or automatic supervisor-agent to execution-agent dispatch. `ic-opt` is the
implemented automation command. `hermes-workflow optimize ... --real` is the
lower-level implementation command behind it.

Release packaging must make OpenBox, TuRBO, and report dependencies available
from the product environment. A development-only path such as
`/tmp/ic_auto_opt_openbox_spike/.venv` is not a valid production dependency.

The Cadence/Spectre/OCEAN environment remains user supplied. Configure it once
before the short product command. Recommended one-user setup:

```bash
mkdir -p ~/.ic-opt
cp /path/to/user/cadence_env.csh ~/.ic-opt/cadence_env.csh
```

Alternatively, put `cadence_env.csh` directly in the project directory or set
`IC_OPT_CADENCE_CSHRC` in your shell. `ic-opt` then discovers the user-supplied
cshrc in this order:

1. explicit `--cadence-cshrc PATH`;
2. `PROJECT_DIR/cadence_env.csh`;
3. environment variable `IC_OPT_CADENCE_CSHRC`;
4. `~/.ic-opt/cadence_env.csh`.

Do not expect `ic-opt` to infer `.bashrc`/`.zshrc` content, and do not hardcode
a Spectre version.

## 1. Create A User Project

Recommended layout:

```text
~/spectre_opt_prj/<project_name>/
├── opt_requirement.md
├── constraints.md
└── context/
```

Use:

- `opt_requirement.md` for the strict optimization request.
- `constraints.md` for supervisor-agent guidance and user preferences.
- `context/` for notes, screenshots, prior reports, or circuit explanations.

Do not hand-build `config/`, `netlists/`, `runs/`, or `reports/`.

## 2. Provide Maestro Point Roots

For each testbench, first run one known-good Maestro/ADE point. The path must be
the point root containing:

```text
<maestro_point_root>/netlist/input.scs
```

For a single testbench, `Maestro Source` contains one `maestro_point_root`.

For multiple testbenches, `Maestro Source` contains a `testbenches:` list. Each
metric must declare `testbench: <id>`. Hermes copies each native netlist bundle
into a namespaced project path and keeps each testbench separate.

## 3. Prepare And Check The Project

From the repo virtualenv:

```bash
./.venv/bin/hermes-workflow check-requirement ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow prepare-from-requirement ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow validate ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow check-project-ready ~/spectre_opt_prj/<project_name>
```

`check-project-ready` does not run real tools. It checks the user request,
rendered config, imported netlist bundles, contract validation, and known report
artifacts.

Expected state before the first optimizer run:

```text
project readiness: pass
readiness: ready_for_first_run
```

## 4. Run The Optimizer

Preferred one-command route:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/<project_name> \
  --real \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10
```

This wraps intake, preparation, validation, readiness, package, netlist
preparation, dry run, preflight health, approval, optimizer task packaging, real
OpenBox execution, optimizer acceptance, completion, finalization,
visualization, and decision reporting. It stops before recording user
acceptance.

To check the offline orchestration gates without launching Spectre/OCEAN/OpenBox:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/<project_name> \
  --real \
  --dry-orchestration \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10
```

Manual equivalent: before a real run, the supervisor must build and approve the
execution package. Do not jump directly from readiness to real execution.

```bash
./.venv/bin/hermes-workflow package ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow prepare-netlist ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow dry-run ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow preflight-health ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow approve ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow package-optimizer-task ~/spectre_opt_prj/<project_name> \
  --backend openbox \
  --max-evals 100 \
  --parallel \
  --cadence-cshrc /path/to/user/cadence_env.csh
```

Before a real run, read `docs/TOOLCHAIN_EXECUTION_REFERENCE.md` and use the
user/project Cadence/OpenBox environment. The environment setup path must come
from the user project or user shell setup; do not hardcode a Spectre version.

Manual OpenBox run:

```bash
./.venv/bin/hermes-workflow run-openbox-real ~/spectre_opt_prj/<project_name> \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10 \
  --cadence-cshrc /path/to/user/cadence_env.csh
```

Resource meanings:

- `spectre.parallel_jobs`: how many Spectre child jobs may run at once.
- `spectre.threads_per_run`: Spectre `+mt` threads per individual simulation.
- `optimizer.optimizer_cpu_threads`: Python/OpenBox-side optimizer math threads.

Execution-agent status policy: report start, unexpected failure, completion,
and only low-frequency heartbeat status for long runs. Do not poll every batch.

## 5. Close Out The Run

If using `hermes-workflow optimize ... --real`, the closeout reports are already
generated. If running the manual route, use the report chain:

```bash
./.venv/bin/hermes-workflow check-optimizer-run ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow summarize-optimizer-run ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow finalize-optimizer-run ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow visualize-optimizer-run ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow decide-optimizer-run ~/spectre_opt_prj/<project_name>
```

Only after the user accepts the recommended feasible best-observed candidate,
record the decision:

```bash
./.venv/bin/hermes-workflow record-optimizer-decision ~/spectre_opt_prj/<project_name> \
  --reason "User accepted the current best observed optimizer result."
./.venv/bin/hermes-workflow write-optimizer-final-summary ~/spectre_opt_prj/<project_name>
./.venv/bin/hermes-workflow check-project-ready ~/spectre_opt_prj/<project_name>
```

Expected state after accepted closeout:

```text
project readiness: pass
readiness: ready_for_closeout_review
```

## 6. Read The Final Artifacts

Primary user-facing report:

```text
reports/optimizer_final_summary.md
```

Supporting reports:

```text
reports/optimizer_insight_report.md
reports/optimizer_decision_report.md
reports/optimizer_supervisor_decision.md
reports/project_readiness_report.json
```

Important boundary: the accepted point is `best observed`, not a mathematical
global optimum certificate.

`decide-optimizer-run` must not present a non-feasible candidate as the primary
recommended run when any feasible candidate exists. Constraint-failed candidates
are diagnostic evidence, not acceptance targets.

## Common Failure Meanings

- `metric_check_failed`: OCEAN returned missing, non-scalar, or invalid metric
  output for that candidate/testbench.
- `constraint_failed`: real tools ran, but the candidate did not satisfy one or
  more user constraints.
- `real_check_failed`: Spectre/OCEAN result artifacts or manifests failed
  structural checks.
- Few or zero feasible points: review constraints, FoM, variable bounds, and
  whether the initial Maestro point roots match the approved formulas.
- Missing netlist sidecars: provide the Maestro point root and let Hermes copy
  the full `netlist/` bundle; do not hand-pick only `input.scs`.
