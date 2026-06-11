# IC Auto Opt Workflow v0.1.5

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

Before a fresh real run, especially when an AI agent is operating the tool, run
a doctor check first:

```bash
ic-opt /path/to/project --doctor
```

For a remote Linux EDA server, keep the project on the server and run:

```bash
ic-opt --ssh-profile eda-lab /remote/path/to/project --real
```

The same command can also be called by an AI agent. The agent should operate the
tool, run doctor before fresh real optimization, and explain the reports; the
deterministic optimization work is done by the CLI.

The platform-neutral agent skill is available in the source tree at
`skills/ic-opt/SKILL.md`. If you installed the package with `pip`, locate the
packaged copy with:

```bash
hermes-workflow agent-skill-path
```

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
- Generates decision reports, insight reports, and PNG FoM/diagnostic plots.
  Optional OpenBox
  advanced dependencies add HTML/JSON surrogate visualization artifacts.
- Supports continuing an existing run, for example adding 40 more evaluations
  after the first 100.
- Supports remote SSH execution: the Python optimizer can run on your local
  Linux/macOS/Windows workstation while Spectre/OCEAN run on a remote Linux EDA
  server through passwordless OpenSSH.
- Provides a platform-neutral agent skill for any shell-capable AI agent.

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
python -m pip install -r requirements-product.txt
```

If your server's `python3` is older than 3.11, use whatever Python 3.11+ command
your administrator provides, such as `python3.11` or `python3.12`.

On macOS, install Python 3.11+ and Git first, for example with Homebrew:

```bash
brew install python@3.11 git
python3 -m venv .venv
```

On Windows, the recommended path is WSL2 Ubuntu because it gives you normal
Linux shell, Python, Git, and OpenSSH behavior:

```bash
# inside WSL2 Ubuntu
sudo apt update
sudo apt install python3 python3-venv python3-pip git openssh-client
python3 -m venv .venv
```

Native Windows PowerShell is theoretically possible for remote mode, but it has
not been release-validated. If you choose native Windows, verify Python 3.11+,
`ssh`, `scp`, and local `tar` yourself before running `ic-opt`. WSL2 is the
recommended Windows path for now.

Advanced OpenBox surrogate visualization is optional. The base optimizer,
Spectre/OCEAN execution, decision report, insight report, continuation, and
project doctor do not require `pyrfr`. Install the advanced dependencies only if
you need OpenBox's advanced surrogate verification / importance views:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install swig
swig -version
python -m pip install --no-build-isolation pyrfr==0.9.0
python -m pip install -r requirements-advanced.txt
```

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

If `pyrfr` fails with `fatal error: Python.h: No such file or directory`, your
Python development headers are missing. Ask your administrator to install the
package matching the Python used by your `.venv`:

```bash
# Ubuntu / Debian
sudo apt install swig build-essential python3-dev

# RHEL / CentOS / Rocky / AlmaLinux
sudo dnf install swig gcc gcc-c++ python3-devel
```

For Python 3.11 specifically, the package may be named `python3.11-dev` or
`python3.11-devel`, depending on the distribution. If you do not have `sudo`,
ask your administrator for one of these: matching Python development headers,
`swig`, a compiler toolchain, or a micromamba/conda environment that already
contains them.

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

Each `maestro_point_root` must be the leaf Maestro/ADE run directory that
contains both `netlist/` and `psf/`, and
`<maestro_point_root>/netlist/input.scs` must exist. A typical path looks like:

```text
~/simulation/<library>/<cell>/<test_name>/results/maestro/Interactive.<N>/<point>/<run_name>/
```

Use the final `<run_name>/` directory. Do not use the parent `Interactive.<N>`
directory, the `<point>` directory, or the `netlist/` subdirectory itself.

Objective expressions combine extracted scalar metric names, not OCEAN
expressions. Use `direction: minimize` for lower-is-better FoM. Use
`direction: maximize` for higher-is-better FoM; the tool keeps the user FoM and
internally minimizes `-FoM` for feasible candidates.

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

### 7. Remote SSH Mode

Remote mode is for the common case where your laptop or workstation can install
Python packages, but Cadence/Spectre/OCEAN are only available on a Linux EDA
server.

The project folder stays on the remote server and keeps the same layout as local
mode:

```text
/remote/path/to/my_mixer_opt/
  opt_requirement.md
  constraints.md          # optional
  cadence_env.csh         # remote Cadence setup file
```

`--ssh-profile` is the SSH target that your local OpenSSH client understands.
It can be a raw target such as `user@server`, but a stable alias in
`~/.ssh/config` is recommended because it keeps `ic-opt` commands short and
repeatable.

Configure passwordless SSH yourself, the same way you would for other EDA bridge
tools. A typical `~/.ssh/config` entry on your local machine is:

```sshconfig
Host eda-lab
  HostName your.eda.server
  User your_user_name
  IdentityFile ~/.ssh/id_ed25519
```

If you do not already have an SSH key, create one on the local machine:

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

Copy the public key to the remote EDA server. If `ssh-copy-id` is available:

```bash
ssh-copy-id eda-lab
```

If `ssh-copy-id` is not available, ask your server administrator how to add
`~/.ssh/id_ed25519.pub` to the remote `~/.ssh/authorized_keys`.

The first SSH connection may ask you to trust the remote host key. Do this once
interactively:

```bash
ssh eda-lab true
```

Then verify that the connection does not ask for a password:

```bash
ssh -o BatchMode=yes eda-lab true
```

`BatchMode=yes` is important. If this command fails, `ic-opt --ssh-profile` is
not ready yet.

Before running optimization, also verify the remote project path:

```bash
ssh eda-lab 'test -f /remote/path/to/my_mixer_opt/opt_requirement.md'
ssh eda-lab 'test -f /remote/path/to/my_mixer_opt/cadence_env.csh'
```

Then run the same workflow with `--ssh-profile`:

```bash
ic-opt --ssh-profile eda-lab /remote/path/to/my_mixer_opt --doctor

ic-opt --ssh-profile eda-lab /remote/path/to/my_mixer_opt \
  --real \
  --max-evals 80 \
  --batch-size 10 \
  --parallel-jobs 6

ic-opt --ssh-profile eda-lab /remote/path/to/my_mixer_opt \
  --continue 20 \
  --batch-size 10 \
  --parallel-jobs 6
```

For remote multi-testbench projects, start conservatively with
`--parallel-jobs 4` to `--parallel-jobs 8`. `parallel_jobs` is candidate-level
concurrency, not per-testbench concurrency. High values such as 24 or 36 can
hit SSH server limits and produce transport errors like
`kex_exchange_identification: Connection closed by remote host`.

If the remote Cadence setup file is not
`/remote/path/to/my_mixer_opt/cadence_env.csh`, pass the remote path:

```bash
ic-opt --ssh-profile eda-lab /remote/path/to/my_mixer_opt \
  --real \
  --cadence-cshrc /remote/path/to/cadence_env.csh
```

Reports are kept on the remote server under `PROJECT/reports/` and mirrored to
your local machine under:

```text
~/.ic-opt/remote_runs/<ssh-profile>/<project-hash>/reports/
```

Remote mode does not install Cadence, OpenBox, or this Python package on the EDA
server. It uses SSH to run the same canonical Spectre/OCEAN commands remotely
and mirrors the resulting reports back to the local optimizer environment.

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
- run `ic-opt PROJECT --doctor` before a fresh real run,
- run `ic-opt`,
- wait for completion,
- read the reports,
- explain the recommended point, feasible count, failure categories, and whether
  continuation is worth doing.

Give your agent the platform-neutral skill before asking it to operate the tool:

```text
skills/ic-opt/SKILL.md
```

For a pip-installed copy, ask the tool where the packaged skill lives:

```bash
hermes-workflow agent-skill-path
```

The skill is not tied to one agent platform. Any agent that can read files and
run shell commands can use it.

The agent should not rewrite OCEAN formulas, parse PSF directly, hand-pick
optimizer points, or change resource settings unless the user explicitly asks.

## Repository Layout

```text
src/hermes_workflow/        Python package and CLI implementation
vendor/open-box/            vendored OpenBox backend used by the product env
skills/ic-opt/              platform-neutral agent skill
examples/                   requirement examples for users
docs/                       user, agent, and release manuals
tests/                      regression tests
tools/                      development helper scripts
requirements-product.txt    product Python dependencies
requirements-advanced.txt   optional OpenBox advanced visualization dependencies
pyproject.toml              package metadata and console scripts
```

## More Documentation

- `docs/USER_GUIDE_CN.md`: beginner-friendly Chinese user guide.
- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`: product quickstart.
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`: known-good tool execution rules.
- `docs/TROUBLESHOOTING_CN.md`: common errors, likely causes, and fixes.
- `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`: requirement file
  format.
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`: platform-neutral agent operating
  manual.
- `docs/AGENT_USER_QUICKSTART_CN.md`: short Chinese agent usage guide.
- `docs/GITHUB_PUBLISH_GUIDE.md`: first GitHub publication checklist.

## Version

Current release: `v0.1.5`.

This release has been clean-installed from GitHub and validated on real
multi-testbench Mixer optimization flows, including local continuation and
remote SSH execution:

```text
local: 100 real evaluations -> continuation by 40 -> 140 accepted cumulative evaluations
remote: 80 real evaluations -> continuation by 20 -> 100 accepted cumulative evaluations
```

Remote SSH users should keep `--parallel-jobs` conservative. For normal
multi-testbench work, start around 4-8; higher values can hit SSH server limits
before they improve optimizer quality.

## License

This project is released under the MIT License. See `LICENSE`.
