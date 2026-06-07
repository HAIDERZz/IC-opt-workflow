# IC Auto Opt Workflow v0.1

IC Auto Opt Workflow is a file-driven optimization workflow for Cadence
Spectre/OCEAN-based analog/RF circuit design. It turns a structured
`opt_requirement.md` project into reproducible optimizer runs, real Spectre
simulations, OCEAN metric extraction, and supervisor-friendly reports.

The v0.1 product goal is practical:

```text
Prepare PROJECT_DIR -> run ic-opt PROJECT_DIR --real -> read reports
```

For supported agent runtimes, the same flow can be started from a short
`/ic-opt PROJECT_DIR --real` request. The deterministic core is still the
`ic-opt` command, so users can run it directly without depending on chat.

## What v0.1 Can Do

- Parse a structured `opt_requirement.md` into project YAML configs.
- Import one or more Maestro/ADE point roots as native Spectre netlist bundles.
- Run OpenBox batch optimization over discrete/quantized design variables.
- Launch real Spectre simulations and OCEAN metric extraction.
- Support multi-testbench candidate evaluation, for example CG/NF, IIP3, and
  P1dB testbenches for one mixer candidate.
- Generate optimizer decision reports, insight reports, FoM plots, and OpenBox
  advanced visualization artifacts.
- Continue an existing optimizer run with additional evaluations.
- Install starter runtime assets for Claude and OpenCode style agent workflows.

## Current Boundaries

- This project does not replace Cadence Virtuoso, Spectre, or OCEAN.
- Users must provide valid Maestro/ADE exported point roots.
- Users must provide a working Cadence shell setup file such as
  `PROJECT_DIR/cadence_env.csh`.
- The optimizer reports the best observed feasible point. It does not claim a
  mathematical global optimum.
- No license is selected in this package yet. Keep the GitHub repository private
  or add a real `LICENSE` before public release.

## Repository Layout

```text
src/hermes_workflow/        Python package and CLI implementation
agent_runtime/              Runtime adapter assets, currently OpenCode
claude_skills/              Claude /ic-opt skill asset
examples/                   User-facing requirement examples
docs/                       Product docs and operating manuals
tests/                      Regression tests
tools/                      Small development checks
requirements-product.txt    Product Python dependencies
pyproject.toml              Python package metadata and console scripts
```

## Install

Create one product-level Python environment. Do not create a virtualenv inside
each optimization project.

```bash
cd /path/to/ic-auto-opt-workflow-v0.1
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -m pip install -e .
```

Check the command:

```bash
./.venv/bin/ic-opt --help
```

## Prepare A Project

Create a user project directory:

```bash
mkdir -p ~/spectre_opt_prj/my_mixer_opt
```

Put these files in it:

```text
~/spectre_opt_prj/my_mixer_opt/
  opt_requirement.md
  constraints.md                 # optional but recommended
  cadence_env.csh                # user/project Cadence environment setup
```

Use the examples in:

```text
examples/spectre_maestro_project/
```

For multi-testbench projects, `opt_requirement.md` should list each Maestro
point root and route each metric to the correct testbench.

## Run

Offline gate check without launching Spectre/OCEAN:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/my_mixer_opt \
  --real \
  --dry-orchestration \
  --max-evals 100 \
  --batch-size 10
```

Real optimization:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/my_mixer_opt \
  --real \
  --max-evals 100 \
  --batch-size 10
```

If your project does not contain `cadence_env.csh`, pass it explicitly:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/my_mixer_opt \
  --real \
  --cadence-cshrc /path/to/cadence_env.csh
```

Continuation after a completed run:

```bash
./.venv/bin/hermes-workflow continue-openbox-real ~/spectre_opt_prj/my_mixer_opt \
  --additional-evals 40 \
  --batch-size 10 \
  --cadence-cshrc ~/spectre_opt_prj/my_mixer_opt/cadence_env.csh
```

Do not add `--parallel-jobs` during continuation unless you intentionally want
to change resources. The continuation path should inherit the project
`config/spectre.yaml` settings so all optimizer evidence remains comparable.

## Read Results

Important reports:

```text
reports/optimizer_flow_run_report.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.md
reports/optimizer_final_summary.md
```

Useful visual artifacts:

```text
reports/optimizer_visuals/
reports/openbox_advanced_visualization/
```

## Agent Runtime Use

After installing runtime adapter assets, a user can ask a supported agent
runtime with a short request:

```text
/ic-opt /path/to/project --real
```

The expected role model is:

```text
user -> current runtime supervisor agent -> same-runtime execution subagent
```

The deterministic workflow still runs through Hermes file contracts and the
`ic-opt`/`hermes-workflow` commands. The agent should not rewrite formulas,
parse PSF directly, hand-pick optimizer points, or change resource settings
unless the user explicitly asks.

See:

```text
docs/AGENT_USER_QUICKSTART_CN.md
docs/AGENT_OPTIMIZER_USAGE_MANUAL.md
docs/AGENT_INTEGRATION_STATUS.md
```

## More Documentation

- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`: product quickstart.
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`: known-good real tool execution rules.
- `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`: requirement file
  format.
- `docs/USER_GUIDE_CN.md`: beginner-friendly Chinese usage guide.
- `docs/GITHUB_PUBLISH_GUIDE.md`: first GitHub publication checklist.
- `CONTRIBUTING.md`: contributor setup and boundaries.

## License

No license has been selected for this v0.1 snapshot. See
`LICENSE_NOT_SELECTED.md`. Until a real `LICENSE` file is added, do not treat
this repository as open source for reuse or redistribution.

## Release Notes

See `RELEASE_NOTES_v0.1.md`.
