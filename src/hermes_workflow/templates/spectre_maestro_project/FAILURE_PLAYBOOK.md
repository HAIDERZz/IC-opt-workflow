# Failure Playbook

Use this file for project-specific recovery notes after a doctor check, a
real run, or another optimizer workflow command reports an actionable
failure. This file is prose for humans and agents; nothing here is read by
the workflow itself.

When a command fails, read the structured report before writing a note here:

- `hermes-workflow check-requirement` / `prepare-from-requirement` failures:
  read `reports/requirement_intake_report.json`. Each issue carries a
  `code` (for example `REQUIREMENT_SECTION_MISSING`), `stage`, `component`,
  `message`, `likely_cause`, and `recommended_action`.
- `hermes-workflow check-project-ready` / `ic-opt <project> --doctor`
  failures: read `reports/project_readiness_report.json`.
- A failed or partial real run: for `optimize`, read
  `reports/optimizer_run_report.json` (OpenBox) or
  `reports/native_turbo_optimizer_report.json` (native TuRBO); for `fix_run`,
  read the fix-run report under the same project `reports/` directory.

Record, per incident: the diagnostic `code`, the root cause once understood,
and the recovery action that worked (for example: a corrected
`model_section`, a fixed absolute path, an approval field that was not
exactly `true`). Do not record machine-readable overrides here; a fix that
must change behavior belongs in `opt_requirement.md`, followed by
`prepare-from-requirement` to re-render `config/`.
