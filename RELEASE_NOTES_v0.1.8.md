# IC Auto Opt Workflow v0.1.8

Release date: 2026-06-17

v0.1.8 adds the verified fix-run workflow to the release package and updates
the public requirement templates, user docs, and agent skill around that
contract.

## Fix-Run Workflow

- Added `Workflow.mode: fix_run` for fixed-point Spectre/OCEAN
  characterization runs.
- Added fixed-point input through the `Fixed Points` section of
  `opt_requirement.md`.
- Added waveform CSV export through the `Waveform Exports` section.
- Added `reports/fix_run_report.json` as the parent fix-run report.
- Added child waveform export manifests and CSV artifact paths under each
  successful testbench/corner child run.
- Added fix-run child-level parallelism through `Spectre Settings.parallel_jobs`.
  `threads_per_run` remains per Spectre process, and fixed points remain serial.
- Fix-run intentionally does not create optimizer state or optimizer decision
  reports.

The release template `examples/spectre_maestro_project/opt_requirement.fix_run.md`
is based on the real validated 15-corner Mixer requirement. It keeps the
verified structure and replaces local machine paths with placeholders.

## Real Workflow Evidence

The v0.1.8 fix-run contract was validated with:

- local 15-corner fix-run workflow
- remote 15-corner fix-run workflow
- local and remote `parallel_jobs: 8` fix-run validation
- TT/SS/FF model sections and five corner variable values per section
- 15 child result manifests
- 15 scalar metric manifests
- 15 waveform export manifests
- 15 `nf_pnoise.csv` waveform exports
- no optimizer state artifacts

The validated pnoise waveform expression form is:

```text
getData("NF" ?result "pnoise")
```

## Local And Remote Support

Fix-run uses the same product commands as optimization:

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

There is no separate fix-run command-line switch. The mode comes from
`PROJECT_DIR/opt_requirement.md`.

## Documentation And Templates

- Updated `README.md` for optimize and fix-run modes.
- Updated Chinese user and agent quickstarts.
- Updated the agent operator skill in `skills/ic-opt/SKILL.md`.
- Updated `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`.
- Added `opt_requirement.fix_run.md` to examples and packaged templates.
- Updated release checklist, publishing guide, toolchain reference,
  troubleshooting, terminology, handoff, and production quickstart docs.

## Carried Forward Capabilities

- Requirement-driven first-run settings.
- Local and remote real optimization.
- OpenBox GP+EIC, OpenBox PRF+EIC, and native TuRBO strategy support.
- Multi-testbench and multi-corner optimization support.
- `output_format: psfxl` metric flow.
- Real license probe doctor gate.
- Sanitized Spectre/OCEAN command trace artifacts.
- Optimizer CPU thread-limit runtime audit.
