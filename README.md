# IC Auto Opt Workflow v0.1.2

IC Auto Opt Workflow helps analog/RF IC designers run repeatable Spectre/OCEAN
optimization from a project folder.

You write the design variables, metric formulas, constraints, and optimizer
settings in `opt_requirement.md`. The tool then prepares YAML configs, imports
Maestro/ADE exported netlists, runs OpenBox optimization, launches Spectre,
extracts metrics with OCEAN, and writes reports that are easy for a human or an
AI agent to read.

The main command is:

```bash
ic-opt /path/to/project --real
```

The same command can also be called by an AI agent. The agent should operate the
tool and explain the reports; the deterministic optimization work is done by the
CLI.

## What This Tool Does

- Converts a structured `opt_requirement.md` into project `config/*.yaml`.
- Imports one or more Maestro/ADE point roots as Spectre netlist bundles.
- Runs OpenBox over discrete or quantized IC design variables.
- Runs real Spectre simulations and OCEAN metric extraction.
- Supports multi-testbench evaluation, for example one Mixer candidate measured
  by CG/NF, IIP3, and P1dB testbenches.
- Uses the same model for one or more testbenches. A single testbench is a valid
  special case; multiple testbenches are only needed when one candidate's
  metrics come from different Maestro/ADE setups.
- Generates decision reports, insight reports, FoM plots, and OpenBox HTML/JSON
  visualization artifacts.
- Supports continuing an existing run, for example adding 40 more evaluations
  after the first 100.
- Provides starter runtime assets for agent workflows such as Claude and
  OpenCode.

## What This Tool Does Not Provide

- It does not include Cadence Virtuoso, Spectre, OCEAN, PDK files, or licenses.
- It does not replace your Maestro/ADE setup. You still need a known-good
  Maestro/ADE point root for each testbench.
- It reports the best observed feasible point. It does not prove a mathematical
  global optimum.
- The workflow can automate Cadence tool usage, but it does not grant access to
  Cadence software, PDKs, or simulator licenses.

## Quick Start

### 1. Install The Tool Once

Create one Python environment for the tool itself. Do not create a virtualenv
inside every optimization project.

```bash
git clone https://github.com/HAIDERZz/IC-opt-workflow.git
cd IC-opt-workflow

python3 --version  # must be Python 3.11 or newer
python3 -m venv .venv
```

Activate the environment with the command that matches your shell:

```bash
# bash / zsh
source .venv/bin/activate
```

```csh
# csh / tcsh, common on EDA servers
source .venv/bin/activate.csh
```

Then install dependencies:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install swig
swig -version
python -m pip install --no-build-isolation pyrfr==0.9.0
python -m pip install -r requirements-product.txt
```

If your server's `python3` is older than 3.11, use whatever Python 3.11+ command
your administrator provides, such as `python3.11` or `python3.12`.

OpenBox may build `pyrfr` during installation. That build needs a `swig`
command and a C/C++ compiler. The `python -m pip install swig` step above is the
lowest-friction user-space path. The important check is `swig -version`: do not
continue until that command works in the same shell where you run `pip`.

If you use the PyPI `swig` package, install `pyrfr` before the full requirements
with `--no-build-isolation`. Without that flag, `pyrfr`'s isolated build
environment can call `.venv/bin/swig` but fail with `ModuleNotFoundError: No
module named 'swig'`.

If you installed `swig` into `.venv` but still see `command 'swig' failed`, the
virtual environment is probably not on `PATH`. Run:

```bash
# bash / zsh
source .venv/bin/activate
swig -version
```

```csh
# csh / tcsh
source .venv/bin/activate.csh
swig -version
```

or, without shell activation:

```bash
env PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python -m pip install -r requirements-product.txt
```

If `swig -version` still does not work on your server, ask your administrator to
install the system packages instead:

```bash
# Ubuntu / Debian
sudo apt install swig build-essential python3-dev

# RHEL / CentOS / Rocky / AlmaLinux
sudo dnf install swig gcc gcc-c++ python3-devel
```

If you do not have `sudo`, ask your administrator for one of these: a newer
Python module, `swig`, a compiler toolchain, or a micromamba/conda environment
that already contains `swig`.

Check that the command is available:

```bash
./.venv/bin/ic-opt --help
```

### 2. Prepare One Optimization Project

Create a project folder for your circuit:

```bash
mkdir -p ~/spectre_opt_prj/my_mixer_opt
```

Put these files in it:

```text
~/spectre_opt_prj/my_mixer_opt/
  opt_requirement.md      # required
  constraints.md          # optional, recommended for human/agent guidance
  cadence_env.csh         # recommended Cadence setup file
```

The Cadence setup file should be the environment you normally use to run
Spectre/OCEAN. The tool should not hard-code a specific Spectre version.

Example requirement files are in:

```text
examples/spectre_maestro_project/
```

`opt_requirement.md` may describe one testbench or multiple testbenches. For
multi-testbench optimization, list each Maestro/ADE point root and map each
metric to the correct testbench. There is no fixed maximum number of
testbenches in the file format; simulation time, license availability, disk
space, and `parallel_jobs` are the real limits.

### 3. Run A Doctor Check

Before launching real simulations, run:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/my_mixer_opt --doctor
```

The doctor check verifies the requirement file, Cadence setup path, Python
toolchain, generated configs, imported netlist bundles, and continuation
artifacts. It does not launch Spectre/OCEAN.

If your Cadence setup file is somewhere else:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/my_mixer_opt \
  --doctor \
  --cadence-cshrc /path/to/cadence_env.csh
```

### 4. Run A Dry Gate

This checks the workflow without launching Spectre/OCEAN:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/my_mixer_opt \
  --real \
  --dry-orchestration \
  --max-evals 100 \
  --batch-size 10
```

### 5. Run Real Optimization

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/my_mixer_opt \
  --real \
  --max-evals 100 \
  --batch-size 10
```

For a project without `cadence_env.csh`:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/my_mixer_opt \
  --real \
  --cadence-cshrc /path/to/cadence_env.csh
```

Run real Spectre/OCEAN outside restricted sandboxes. The process needs access to
your Cadence tools, license server, project files, and simulation directories.

### 6. Continue An Existing Run

After reviewing the first result, you can add more evaluations:

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/my_mixer_opt --continue 40
```

When prior optimizer history exists, continuation inherits that history's
resource settings. Do not add `--parallel-jobs` unless you intentionally want to
change resources; mixed resource settings make optimizer evidence harder to
compare and can be rejected by the acceptance audit.

## Read The Results

Start with:

```text
reports/optimizer_decision_report.md
reports/optimizer_insight_report.md
reports/optimizer_final_summary.md
```

Useful machine-readable reports:

```text
reports/optimizer_flow_run_report.json
reports/optimizer_run_acceptance_report.json
reports/optimizer_evaluations.jsonl
```

Useful visual outputs:

```text
reports/optimizer_visuals/
reports/openbox_advanced_visualization/
```

Important wording:

- `best observed` means the best point found in the completed evaluations.
- `feasible` means the point passed the configured constraints.
- `constraint_failed` usually means the circuit simulated but did not meet the
  design requirements.
- `metric_check_failed` usually means the OCEAN formula did not return a valid
  scalar for that candidate.

## Using It With An AI Agent

The preferred user interaction is short:

```text
/ic-opt ~/spectre_opt_prj/my_mixer_opt --real
```

The project requirements should live in files, not in a long chat message. The
agent should:

- read the project files,
- run `ic-opt`,
- wait for completion,
- read the reports,
- explain the recommended point, feasible count, failure categories, and whether
  continuation is worth doing.

The agent should not rewrite OCEAN formulas, parse PSF directly, hand-pick
optimizer points, or change resource settings unless the user explicitly asks.

## Repository Layout

```text
src/hermes_workflow/        Python package and CLI implementation
vendor/open-box/            vendored OpenBox backend used by the product env
agent_runtime/              starter runtime assets for agent workflows
claude_skills/              Claude skill asset
examples/                   requirement examples for users
docs/                       detailed manuals and project notes
tests/                      regression tests
tools/                      development helper scripts
requirements-product.txt    product Python dependencies
pyproject.toml              package metadata and console scripts
```

## More Documentation

- `docs/USER_GUIDE_CN.md`: beginner-friendly Chinese user guide.
- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`: product quickstart.
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`: known-good tool execution rules.
- `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`: requirement file
  format.
- `docs/AGENT_USER_QUICKSTART_CN.md`: short agent usage guide.
- `docs/GITHUB_PUBLISH_GUIDE.md`: first GitHub publication checklist.

## Version

Current release: `v0.1.2`.

This release has been clean-installed from GitHub and validated on a real
multi-testbench Mixer optimization flow:

```text
100 real evaluations
-> user-style continuation by 40 more evaluations
-> 140 accepted cumulative evaluations
```

## License

This project is released under the MIT License. See `LICENSE`.
