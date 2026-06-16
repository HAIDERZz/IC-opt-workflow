# Fix-Run Simulation Workflow Spec

Date: 2026-06-16
Status: Draft for review
Scope: `ic-auto-opt-workflow` development package

## Problem

Some users do not want optimization. They want to run one specified design point, or a small list of specified design points, across the same real Spectre/OCEAN infrastructure used by the optimizer. The output is an auditable simulation archive: PSF data, scalar metrics when requested, waveform CSV exports when requested, command traces, and manifests that preserve the point, testbench, corner, and OCEAN expression used to produce each artifact.

The workflow must not pretend that a single fixed point is an optimizer run. It must not use `max_evaluations: 1`, and it must not create optimizer state or optimizer decision reports.

## Goals

- Support a `fix_run` workflow mode configured in `opt_requirement.md`.
- Run one or more user-specified design points.
- Expand each point across configured testbenches and process corners.
- Reuse the existing real-run, multi-corner, local/remote Spectre/OCEAN, license/doctor, command-trace, and aggregation paths.
- Export waveform CSV artifacts from each corner PSF using OCEAN.
- Keep the product CLI free of variable, strategy, budget, thread, and corner override options.
- Preserve backward compatibility for current optimizer requirements that do not contain a `Workflow` section.

## Non-Goals

- No optimizer algorithm changes.
- No continuation semantics for fix-run in the first version.
- No new CLI options for design variables, max evaluations, parallel jobs, Spectre threads, process corners, or waveform formulas.
- No support for `psfascii`.
- No replacement of the scalar metric path.
- No attempt to convert arbitrary OCEAN data structures into a single universal CSV schema beyond what `ocnPrint` emits for a waveform object.

## User Contract

Existing optimizer use remains:

```bash
ic-opt /path/to/project --real
```

For fix-run, the command stays the same. The requirement file selects the mode:

```bash
ic-opt /path/to/project --real
```

The product CLI dispatches by `Workflow.mode`:

- Missing `Workflow` section means optimizer mode for backward compatibility.
- `Workflow.mode: optimize` means optimizer mode.
- `Workflow.mode: fix_run` means fixed-point simulation mode.

The CLI chooses a real execution. The requirement file supplies points, variables, corners, waveform exports, parallelism, Spectre threads, and timeout.

## Requirement Format

### Workflow Section

```yaml
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

Rules:

- `mode` is `optimize` or `fix_run`.
- If `Workflow` is absent, the system behaves as `mode: optimize`.
- `starting_run_id` is optional and must match the existing run id pattern `real_NNN`.
- Multiple fixed points allocate consecutive run ids from `starting_run_id`.

### Fixed Points Section

```yaml
schema_version: "1.0"
points:
  - candidate_id: user_point_001
    parameters:
      w_m1: "8u"
      cap_sw: "1.2u"
      r_load: "500"
```

Rules:

- At least one point is required in `fix_run` mode.
- `candidate_id` uses the existing safe candidate id rule.
- `parameters` must contain every design variable required by the rendered netlist.
- Unknown parameter names fail during intake.
- Parameter values are strings and are injected through the existing candidate request path.

### Waveform Exports Section

```yaml
schema_version: "1.0"
exports:
  - name: nf_pnoise
    testbench: cg_nf
    expression: 'getData("NF" ?result "pnoise")'
    output_format: csv
    nil_policy: fail

  - name: pac_vh_db
    testbench: cg_gain
    expression: "db(vh('pac))"
    output_format: csv
    nil_policy: fail
```

Rules:

- `Waveform Exports` is optional when scalar `Metrics` are present.
- `fix_run` mode requires at least one of `Metrics` or `Waveform Exports`.
- Each export belongs to exactly one named testbench.
- The default corner scope is all configured corners.
- `output_format` is only `csv`.
- Expressions must not contain template placeholders or file-writing primitives such as `outfile`.
- The correct pnoise form is `getData("NF" ?result "pnoise")`.

## Required Sections by Mode

Common sections:

- `Project`
- `Maestro Source`
- `Design Variables`
- `Spectre Settings`
- `Approval Checklist`

Optimizer mode additionally requires:

- `Metrics`
- `Constraints`
- `Objective`
- `Optimizer Settings`

Fix-run mode additionally requires:

- `Fixed Points`
- At least one of `Metrics` or `Waveform Exports`

Optional in both modes:

- `Process Corners`

`Constraints`, `Objective`, and `Optimizer Settings` are not used in `fix_run` mode. If present, they may be parsed for compatibility, but fix-run reports must state that they were ignored.

## Execution Model

Fix-run reuses the existing `runs/real` artifact root.

For one fixed point:

```text
runs/real/real_001/
  candidate_request.json
  real_run_manifest.json
  testbenches/<tb_id>/corners/<corner_id>/
    psf/
    metrics/
      metric_probe.ocn
      ocean.log
      ocean_scalars.tsv
      metric_result_manifest.json
      waveforms/
        <export_name>.csv
      waveform_export_manifest.json
reports/fix_run_report.json
```

For multiple fixed points:

```text
runs/real/real_001/  # user_point_001
runs/real/real_002/  # user_point_002
reports/fix_run_report.json
```

The existing run id validator remains intact for the first version. The new workflow maps fixed points to existing `real_NNN` run ids instead of introducing a new `fix_NNN` id family.

## OCEAN CSV Export

The OCEAN replay script keeps the scalar metric output path and adds waveform export output after opening the point-specific PSF.

Example generated OCEAN logic:

```skill
selectResult('pnoise)
nf_pnoise = getData("NF" ?result "pnoise")
nf_pnoise_out = outfile("/abs/path/metrics/waveforms/nf_pnoise.csv" "w")
ocnPrint(?output nf_pnoise_out ?separator "," ?numberNotation 'scientific nf_pnoise)
close(nf_pnoise_out)
```

The script writer must validate output paths, export names, and expression hashes before emitting the OCEAN script. CSV files are formal artifacts and must not be written to temporary directories.

## Manifests

### Waveform Export Manifest

Path:

```text
runs/real/<run_id>/testbenches/<tb_id>/corners/<corner_id>/metrics/waveform_export_manifest.json
```

Required fields:

```json
{
  "schema_version": "1.0",
  "workflow_mode": "fix_run",
  "run_id": "real_001",
  "candidate_id": "user_point_001",
  "testbench_id": "cg_nf",
  "corner_id": "tt_temp_27",
  "model_section": "Post_simu_top_tt",
  "corner_variables": {
    "temperature": "27"
  },
  "parameters": {
    "w_m1": "8u",
    "cap_sw": "1.2u"
  },
  "exports": [
    {
      "name": "nf_pnoise",
      "expression": "getData(\"NF\" ?result \"pnoise\")",
      "expression_sha256": "sha256-hex",
      "output_format": "csv",
      "csv_path": "metrics/waveforms/nf_pnoise.csv",
      "status": "pass",
      "issues": []
    }
  ],
  "psf_dir": "psf",
  "ocean_log": "metrics/ocean.log",
  "command_trace": {
    "schema_version": "1.0"
  }
}
```

### Fix-Run Report

Path:

```text
reports/fix_run_report.json
```

Required content:

- `schema_version`
- `workflow_mode`
- `status`
- list of fixed points
- run id assigned to each point
- count of testbench/corner child runs
- scalar metric manifest paths
- waveform export manifest paths
- CSV artifact paths
- failure issues grouped by point, testbench, and corner
- confirmation that optimizer state and optimizer decision reports were not produced

## Local and Remote Behavior

Local:

- Run product doctor when `Spectre Settings.require_license_check` is true.
- Prepare candidate requests from `Fixed Points`.
- Execute each testbench/corner child with the existing local Spectre/OCEAN adapter.
- Write scalar and waveform manifests.
- Write `reports/fix_run_report.json`.

Remote:

- Run remote doctor and license probe through the existing remote doctor path.
- Upload fixed-point candidate requests and rendered netlists.
- Execute remote Spectre/OCEAN through the existing remote adapter.
- Download PSF, scalar outputs, OCEAN logs, waveform CSV files, and manifests.
- Preserve sanitized command traces in local cache and downloaded manifests.

## Error Handling

- Missing `Fixed Points` in `fix_run` mode fails requirement intake.
- `fix_run` with neither scalar metrics nor waveform exports fails requirement intake.
- Unknown fixed-point parameter names fail requirement intake.
- Missing variable values fail before real execution.
- A waveform expression that returns nil fails the export when `nil_policy: fail`.
- Missing CSV output after OCEAN returns zero is a failure.
- OCEAN non-zero return marks the child metric/export status as failed and preserves logs.
- A failed child run does not hide other child artifacts; the parent report records partial results.

## Compatibility

- Existing optimizer requirements without `Workflow` remain valid.
- Existing optimizer reports and state files are unchanged.
- Existing `Metrics` scalar behavior is unchanged.
- Existing `Process Corners` behavior is reused.
- Existing command trace schema is reused and may be embedded in waveform manifests.

## Acceptance Criteria

Code-level acceptance:

- Requirement parser accepts valid `fix_run` requirements without `Optimizer Settings`.
- Requirement parser still requires optimizer sections for optimizer mode.
- Fixed points are converted into existing `CandidateInjectionRequest` objects.
- OCEAN script rendering writes scalar metric output and waveform CSV output without path injection.
- Local and remote adapters persist waveform export manifests.
- Product CLI `--real` dispatches to fix-run when `Workflow.mode: fix_run`.

Workflow acceptance:

- Run one local real fixed point across at least 3 process sections and 10 temperatures.
- Run one remote real fixed point across the same corner set.
- Confirm no optimizer state, optimizer decision report, or optimizer final summary is generated.
- Confirm every child has PSF, OCEAN log, command trace, and waveform export manifest.
- Confirm every requested waveform CSV exists and is non-empty.
- Randomly inspect one `tt`, one `ss`, and one `ff` corner and verify model section, temperature, user parameters, expression, CSV path, and command trace.

