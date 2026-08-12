# IC Auto Opt Workflow

IC Auto Opt is a requirement-driven workflow for real IC Spectre/OCEAN
optimization and fixed-point characterization. A user describes the circuit,
metrics, search space, simulator resources, and workflow mode in
`opt_requirement.md`; the product CLI validates the project, prepares netlists,
runs Spectre/OCEAN locally or through SSH, and writes auditable reports.

Current release modes:

- `optimize`: run OpenBox or native TuRBO over approved design variables.
- `fix_run`: run user-specified fixed design points and export requested
  waveform CSV artifacts without creating optimizer state.

Both modes are selected in `PROJECT_DIR/opt_requirement.md`. There is no
separate fix-run command-line switch.

## Install From GitHub

Use HTTPS unless your site requires SSH Git access:

```bash
git clone https://github.com/HAIDERZz/IC-opt-workflow.git
cd IC-opt-workflow
```

IC Auto Opt requires Python 3.11 or newer for the interpreter used to create
the virtual environment (`pyproject.toml` declares `requires-python = ">=3.11"`,
and the source uses 3.11-only syntax). EDA servers often ship an older default
`python3`; use the site's `python3.11` (or newer) command if so.

Create the Python environment from the repository root:

```bash
python3 -m venv .venv   # use python3.11 (or newer) here if the site python3 is older
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Check the entrypoints:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
./.venv/bin/hermes-workflow --version
```

`hermes-workflow --version` confirms the installed package version matches the
checkout; `ic-opt` has no separate `--version` flag.

Optional advanced report dependencies are separate. Install `swig` first,
then the rest of the file: pip does not guarantee installing
`requirements-advanced.txt` entries in file order, and building `pyrfr` from
source can fail if `swig` is not already on `PATH`.

```bash
./.venv/bin/python -m pip install swig==4.4.1
./.venv/bin/python -m pip install -r requirements-advanced.txt
```

Install the advanced set only if you need OpenBox advanced surrogate
visualization, hyperparameter-importance views, or SHAP/lightgbm-backed
analysis. Some packages in that set are larger or may need Python development
headers on Linux.

Do not create this virtual environment inside a user optimization project
directory. Keep the tool checkout and each IC optimization project separate.

## Choose Local Or Remote Mode

Use local mode when the same Linux machine can host both:

- the IC Auto Opt Python environment
- Cadence/Spectre/OCEAN/PDK/license access
- the user project directory

Use remote mode when you want the Python control environment on a personal
Linux workstation, macOS machine, or Windows WSL, while Spectre/OCEAN runs on a
separate Linux EDA server through SSH. Remote mode is useful when installing a
Python environment directly on the EDA server is inconvenient.

Controller and Remote Host filesystems are assumed to be isolated in remote
mode. A Remote-owned path is never checked through the Controller filesystem;
it is accessed through the configured SSH transport or explicitly materialized
under the Controller cache. A same-named path that happens to exist on both
machines is not part of the remote-mode contract.

See `CONTEXT.md` for the full remote-mode terminology glossary (Controller,
Remote Host, Controller Cache, Remote-owned Path, Remote Attempt Lock,
Continuation, Remote History Manifest, and related terms).

## SSH Profile For Remote Mode

`--ssh-profile PROFILE` refers to an OpenSSH host profile, usually defined in
`~/.ssh/config` on the control machine.

Example:

```sshconfig
Host eda-lab
  HostName eda-server.example.com
  User username
  IdentityFile ~/.ssh/id_ed25519
```

Check that SSH works before using IC Auto Opt:

```bash
ssh eda-lab 'hostname'
```

The remote `PROJECT_DIR` passed to `ic-opt` is an absolute path on the remote
Linux EDA server. It must contain `opt_requirement.md` and the referenced
Maestro/ADE result point directories. IC Auto Opt reads the remote requirement,
downloads the exported netlists into a local cache under `~/.ic-opt/remote_runs`,
uploads per-run Spectre/OCEAN work directories, downloads results, and writes
the resulting artifacts and reports back to the remote project. Remote Maestro
input existence checks execute `test -f` over SSH: exit status 0 means present,
1 means absent, and any other status is a transport/probe error rather than a
missing file.

For optimizer runs, a pass-status
`reports/optimizer_flow_run_report.json` is the final success marker. It is
published only after the Remote Host has verified the SHA-256 content and
project-relative references of all expected parent and child manifests. A
failure-status flow report is published independently, so an incomplete run can
retain failure evidence without being presented as successful.

A Remote project allows only one active Controller attempt at a time. Before
preparation, IC Auto Opt takes a token-owned lock at
`state/remote_attempt.lock` on the Remote Host; a concurrent Controller
attempt against the same project is rejected. If a prior attempt was
interrupted and left a stale lock, the rejection message points at an
`owner.json` next to the lock directory — inspect it before manually removing
the lock.

Remote command shape:

```bash
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --doctor
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --real
```

## Cadence Environment

Provide a `csh` or `tcsh` Cadence setup file. The workflow discovers it in this
order:

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

The setup must expose `spectre`, `ocean`, and license tools. Do not use
`.bashrc` or `.zshrc` as a Cadence `csh` setup file.

For remote mode, the Cadence setup path is interpreted on the remote Linux EDA
server.

## Product Commands

Local doctor:

```bash
./.venv/bin/ic-opt /path/to/project --doctor
```

Local real run:

```bash
./.venv/bin/ic-opt /path/to/project --real
```

Local optimize-only dry orchestration gate:

```bash
./.venv/bin/ic-opt /path/to/project --real --dry-orchestration
```

This runs the offline orchestration gates through package generation and stops
before the real optimizer backend starts Spectre/OCEAN candidate execution. Use
it only for first-run local optimize projects. It is not the continuation path,
not a fix-run mode, and not the remote execution path in this release.

Continue an existing optimization run:

```bash
./.venv/bin/ic-opt /path/to/project --real --continue N
```

Remote:

```bash
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --doctor
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --real
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --real --continue N
```

`--continue N` only adds budget to an existing optimizer project. It does not
reread a changed `opt_requirement.md`. Continuation keeps the backend already
declared by the generated project config: OpenBox resumes OpenBox history and
native TuRBO resumes native TuRBO history. Native TuRBO reconstructs its active
trust-region state from the accepted trace; because older artifacts do not
contain library RNG state, this is a trace-equivalent continuation rather than
a claim of bit-for-bit equivalence to one uninterrupted process. Every Remote
continuation attempt reruns Remote Doctor against the current host environment
before restoring the frozen snapshot, syncing history, or starting a backend.

## Project Directory

A user project is data-only:

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

Only `opt_requirement.md` is required. Use `constraints.md` for human guidance
and `context/` for notes, screenshots, or previous reports; `context/` is a
purely human reference directory that the workflow never reads. Generated
directories such as `config/`, `netlists/`, `runs/`, `reports/`, `ledger/`,
`state/`, `execution_package/` (the approval manifest gating the first real
run), and `candidate_requests/` (per-candidate optimizer suggestion payloads)
are created by the workflow.

For each testbench, first run one known-good point in Maestro/ADE. The
`maestro_point_root` in `opt_requirement.md` is the Maestro result point
directory itself, not the `input.scs` file and not the `psf/` directory. It
must contain:

```text
<maestro_point_root>/netlist/input.scs
```

A typical Maestro result point looks like:

```text
/home/username/simulation/<virtuoso_library>/<cellview_name>/maestro/results/maestro/Interactive.N/1/<test_name>
```

For example:

```text
/home/username/simulation/Virtuoso_Bridge_test/MixerCS_PSS_IIP3/maestro/results/maestro/Interactive.28/1/Mixer_CS_IIP3
```

`Virtuoso_Bridge_test` and `MixerCS_PSS_IIP3` are illustrative placeholder
names reused across this repository's docs, examples, and templates; they do
not reference a specific design.

Use the actual `Interactive.N` directory and final testbench directory produced
by the Maestro run.

## Requirement Templates

Start from one of these examples:

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.openbox_gp_eic.md
examples/spectre_maestro_project/opt_requirement.turbo.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.history_warm_start.md
examples/spectre_maestro_project/opt_requirement.history_warm_start.multi_corner.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
examples/spectre_maestro_project/opt_requirement.fix_run.metrics_only.md
examples/spectre_maestro_project/opt_requirement.fix_run.multi_testbench.metrics_waveform.md
```

The explicit GP-EIC and TuRBO templates expose both supported optimizer
families. Multi-testbench templates route every metric/export to its owning
testbench. History warm-start examples cover source-point and multi-corner
OpenBox runs. Fix-run examples cover waveform-only, metrics-only, and combined
multi-testbench measurements. Replace all project-specific paths, history
sources, fixed points, corner values, and circuit expressions with reviewed
values.

## Optimize Mode

Optimization requirements define:

- Maestro/ADE point roots and testbench routes
- OCEAN scalar metric expressions
- design variables, legal ranges, and steps
- objective and constraints
- `max_evaluations` and `batch_size`
- Spectre `parallel_jobs` and `threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`, `strategy`, `initialization`, and `random_seed`
- `output_format: psfxl`
- license probe, retention, and artifact policy
- Process Corners and multi-corner policies, when needed
- an Approval Checklist with `metric_formulas_user_approved`,
  `maestro_source_user_approved`, `variable_bounds_user_approved`, and
  `spectre_resource_settings_user_approved` all explicitly `true`; intake
  fails if any field is missing or not `true`

Production strategy choices:

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: openbox`, `strategy: openbox_auto` (explicit OpenBox
  compatibility/auto-selection strategy, used by the multi-testbench and
  history-warm-start templates)
- `algorithm: turbo`, `strategy: turbo_trust_region`

`random_baseline` is for diagnostics, not production optimization.

## History Warm Start

Use `History Warm Start` when a new optimize project should learn from previous
same-circuit runs. This is different from `--continue N`: continuation only adds
budget to the same project and does not reread a changed `opt_requirement.md`.

```yaml
enabled: true
sources:
  - path: /path/to/previous_same_circuit_project
    label: round1
max_observations: 200
warm_start_strategy: topk
```

The section renders to `config/history_warm_start.yaml`. History warm-start is
optimize-only, cannot be combined with `--continue`, and is not supported for
fix-run. It is an OpenBox-only capability. An enabled History Warm Start with a
native TuRBO backend is rejected during requirement intake/project validation;
it is never silently ignored. Use `--continue N` to extend an existing native
TuRBO project.

Current and previous projects must use the exact same variable names. Old
objective and constraint values are not reused; old raw metrics are re-evaluated
with the current requirement. Inspect `reports/history_warm_start_audit.json`,
`reports/history_warm_start_audit.md`, and `openbox.history_warm_start` in
`reports/optimizer_run_report.json` before saying the history was applied.

## Fix-Run Mode

Fix-run requirements define:

- `Workflow.mode: fix_run`
- one or more fixed candidate points
- Maestro/ADE point roots and testbench routes
- Spectre settings and Process Corners
- optional waveform CSV exports, for example
  `getData("NF" ?result "pnoise")`
- the approval checklist used by real runs

Fix-run does not run an optimizer, does not create `state/optimizer_state.json`,
and does not create `reports/optimizer_decision_report.md`.

In fix-run mode, Spectre `parallel_jobs` controls the maximum number of
testbench/corner child runs for one fixed point that may run concurrently.
`threads_per_run` remains the Spectre `+mt` thread count for each child process.
Fixed points are processed serially in this release.

## Read Results

`reports/optimizer_flow_run_report.json` is the overall pass/fail success
marker for a completed optimizer run (local or Remote). Check its status
before treating any other optimizer report as authoritative.

Optimization evidence, common to both backends:

```text
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_flow_run_report.json
reports/optimizer_completion_report.json
reports/optimizer_run_acceptance_report.json
reports/optimizer_finalize_report.json
reports/optimizer_effectiveness_audit.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/optimizer_insight_report.html
reports/optimizer_final_summary.json
reports/optimizer_final_summary.md
reports/requirement_intake_report.json
ledger/experiment_ledger.jsonl
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

Backend-specific run report and evaluation trace (only one pair is written per
project, matching the requirement's `algorithm`):

```text
# algorithm: openbox (openbox_gp_eic, openbox_prf_eic, openbox_auto)
reports/optimizer_run_report.json
reports/optimizer_evaluations.jsonl

# algorithm: turbo (turbo_trust_region, native TuRBO)
reports/native_turbo_optimizer_report.json
reports/native_turbo_optimizer_evaluations.jsonl
```

Conditional evidence:

```text
reports/history_warm_start_audit.json                  (History Warm Start enabled only)
reports/history_warm_start_audit.md                     (History Warm Start enabled only)
reports/openbox_advanced_visualization_manifest.json     (OpenBox advanced visualization only)
reports/multi_testbench_aggregation_report.json          (multi-testbench projects only)
```

Fix-run evidence. The child-run path depends on the project's
testbench/corner shape; all four shapes below still contain
`result_manifest.json`, and `metrics/` holds `metric_result_manifest.json`
and, when waveforms were requested, `waveform_export_manifest.json` plus
`metrics/waveforms/<name>.csv`:

```text
reports/fix_run_report.json

# multi-testbench, per-testbench corners
runs/real/real_001/testbenches/<tb>/corners/<corner>/result_manifest.json

# multi-testbench, no corners
runs/real/real_001/testbenches/<tb>/result_manifest.json

# single testbench, multiple corners
runs/real/real_001/corners/<corner>/result_manifest.json

# single testbench, no corners
runs/real/real_001/result_manifest.json
```

`reports/optimizer_insight_report.html` is the first reader-facing optimization
report. Use it for orientation, but use JSON/JSONL and child manifests for
precise engineering decisions. The report-layer Pareto/trade-off analyzer uses
existing raw metrics; it does not enable OpenBox multi-objective optimizer mode.
Space Compression Advisory uses an OpenBox compressor dry-run and is advisory
only. Suggested ranges are not applied automatically.

For native TuRBO runs, backend-neutral report sections remain useful: best
observed point, measured metrics, evaluation counts, plots, raw-metric
trade-off summaries, and advisory space-compression dry-runs when artifacts
exist. OpenBox-specific sections such as history warm-start application,
advanced surrogate visualization, and parameter importance may be absent or
marked `not_available`.

Do not treat a command exit code alone as acceptance. Check the reports and
artifacts.

## Agent Use

For agent-assisted operation, give the agent:

```text
skills/ic-opt/SKILL.md
PROJECT_DIR
```

The agent should use the product CLI and inspect workflow artifacts before
reporting success.

## Current Release

Version `0.1.10` includes:

- local and remote optimize workflows
- local and remote fix-run workflows
- fix-run child-level parallelism through `Spectre Settings.parallel_jobs`
- waveform CSV export manifests for fix-run child runs
- OpenBox history warm-start for new same-circuit optimize projects
- optimizer insight HTML/JSON/Markdown reports with best-point metrics,
  report-layer raw-metric trade-off summaries, history reuse summaries, and
  advisory space-compression dry-runs
- OpenBox GP+EIC, OpenBox PRF+EIC, and native TuRBO
- multi-testbench and multi-corner support
- psfxl-only metric flow
- real license probe doctor gate
- sanitized Spectre/OCEAN command trace artifacts
- optimizer CPU thread-limit runtime audit
- release examples and agent skill guidance synchronized with the current CLI
- isolated Controller/Remote filesystem handling and atomic Remote transfer
- native TuRBO local/Remote continuation with trace-reconstructed state
- fail-early CLI mode contracts and portable toolchain defaults

See `RELEASE_NOTES_v0.1.10.md`.
