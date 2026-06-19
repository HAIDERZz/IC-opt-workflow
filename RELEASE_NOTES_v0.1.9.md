# IC Auto Opt Workflow v0.1.9

Release date: 2026-06-19

v0.1.9 is the published release for the verified fix-run and release-package
sync work. It supersedes the unpushed v0.1.8 final-sync commit because the
`v0.1.8` tag already existed on an older release commit.

## Fix-Run Workflow

- Added `Workflow.mode: fix_run` for fixed-point Spectre/OCEAN
  characterization runs.
- Added fixed-point input through the `Fixed Points` section of
  `opt_requirement.md`.
- Added waveform CSV export through the `Waveform Exports` section.
- Added `reports/fix_run_report.json` as the parent fix-run report.
- Added child waveform export manifests and CSV artifact paths under each
  successful testbench/corner child run.
- Added local and remote fix-run child-level parallelism through
  `Spectre Settings.parallel_jobs`. `threads_per_run` remains per Spectre
  process, and fixed points remain serial.
- Fix-run intentionally does not create optimizer state or optimizer decision
  reports.

The release template `examples/spectre_maestro_project/opt_requirement.fix_run.md`
is based on the real validated Mixer requirement. It keeps the verified structure
and replaces local machine paths with placeholders.

## Release Package Sync

- Synchronized example requirement templates with packaged templates under
  `src/hermes_workflow/templates/spectre_maestro_project`.
- Added the packaged template config resources that clean installs need.
- Updated user docs, agent docs, troubleshooting, toolchain, release checklist,
  and skill instructions for the current fix-run and doctor contracts.
- Kept internal `docs/superpowers/`, `graphify-out/`, and local research notes
  out of the release package.
- Updated version metadata to `0.1.9`.

## Validation

The release content was verified from the release checkout using the dev
interpreter with `PYTHONPATH=src`:

- full pytest suite: `1194 passed, 13 warnings`
- `ruff check src tests`: passed
- `git diff --check`: clean
- example/template mirror checks: clean
- stale doctor-path drift check: clean
- removed execution-agent user-doc drift check: clean

## Carried Forward Capabilities

- Requirement-driven first-run settings.
- Local and remote real optimization.
- OpenBox GP+EIC, OpenBox PRF+EIC, and native TuRBO strategy support.
- Multi-testbench and multi-corner optimization support.
- `output_format: psfxl` metric flow.
- Real license probe doctor gate.
- Sanitized Spectre/OCEAN command trace artifacts.
- Optimizer CPU thread-limit runtime audit.
