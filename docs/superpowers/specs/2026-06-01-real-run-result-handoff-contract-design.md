# Real-Run Result Handoff Contract Design

## Goal

Add a Hermes-side contract for validating the files returned by the execution agent after the first real Spectre run package has been consumed, without running Spectre, parsing simulator result databases, extracting real metrics, appending optimizer ledger rows, or starting an optimizer loop.

## Problem

Plan C C-4 now prepares a first real-run package after approval:

```text
Hermes approve
Hermes prepare-real-run
runs/real/real_001/input.scs
runs/real/real_001/candidate.json
runs/real/real_001/real_run_manifest.json
```

The next gap is the return path. Once the execution agent uses `virtuoso-bridge-lite` or a local Cadence environment to run the prepared deck, there is no deterministic file contract for reporting what happened back to Hermes.

If this boundary remains informal, future workers may invent incompatible result layouts, skip input-hash attestation, mix raw simulator artifacts with parsed metrics, or write optimizer state before Hermes has validated the first real-run result package.

C-5 closes only the result handoff gap. It does not execute the simulator and does not interpret simulator outputs.

## Scope

Included:

- Define a `result_manifest.json` file written by the execution agent into `runs/real/<run_id>/`.
- Add a Hermes validator for the returned real-run result handoff.
- Add a CLI command named `check-real-run`.
- Verify that the result manifest matches the prepared `real_run_manifest.json`.
- Verify run ID, candidate ID, rendered deck hash, and declared artifact paths.
- Verify the execution outcome is one of the allowed result states.
- Verify artifact paths are project-relative, stay inside the run directory, and exist.
- Write a machine-readable `reports/real_run_check_report.json`.
- Add unit and CLI tests using sanitized fixtures.
- Update documentation and progress state.

Excluded:

- Running Spectre.
- Running Virtuoso.
- Launching shell subprocesses.
- Parsing PSF, PSF ASCII, raw, or other simulator databases.
- Computing real metrics.
- Evaluating objective or constraints from real results.
- Appending `ledger/experiment_ledger.jsonl`.
- Writing `state/optimizer_state.json` or `state/best_candidate.json`.
- Implementing multi-candidate execution.
- Implementing an optimizer loop.
- Committing real `input.scs`, Spectre logs, or proprietary simulator outputs.

## Current Route

C-5 extends the post-approval route after C-4:

```text
Hermes prepare-real-run
runs/real/real_001 package
execution agent runs Spectre outside Hermes
execution agent writes result_manifest.json and declared artifacts
Hermes check-real-run
reports/real_run_check_report.json
future metric extraction consumes validated handoff
```

The command is intentionally one step after execution but one step before metric extraction. It validates the returned file contract so later plans can safely parse metrics and update optimizer state.

## Responsibility Split

Hermes owns:

- The prepared run package from C-4.
- The result handoff schema.
- Validation of returned result metadata and artifact paths.
- The `reports/real_run_check_report.json` report.

The execution agent owns:

- Consuming `runs/real/<run_id>/input.scs`.
- Running Spectre or equivalent simulator flow through approved tool-side mechanisms.
- Preserving C-4 immutable inputs.
- Writing `result_manifest.json`.
- Placing declared logs and raw artifacts under `runs/real/<run_id>/`.

Hermes does not trust the execution agent's chat response. Hermes trusts only validated files.

## Result Manifest Contract

The execution agent writes:

```text
runs/real/<run_id>/result_manifest.json
```

For C-5, the result manifest should use this shape:

```json
{
  "schema_version": "1.0",
  "run_id": "real_001",
  "candidate_id": "real_001",
  "status": "succeeded",
  "started_at_utc": "2026-06-01T00:20:00Z",
  "completed_at_utc": "2026-06-01T00:21:00Z",
  "simulator": {
    "engine": "spectre_x",
    "preset": "ax",
    "command_label": "external_spectre_run"
  },
  "prepared_input_scs": "runs/real/real_001/input.scs",
  "prepared_input_sha256": "<sha256 from real_run_manifest.json>",
  "log_file": "runs/real/real_001/spectre.log",
  "artifact_files": [
    "runs/real/real_001/artifacts/psf_summary.txt"
  ],
  "notes": "optional execution-agent note"
}
```

Allowed `status` values:

- `succeeded`
- `failed`

The `failed` status is valid handoff data, not a Hermes validation failure, as long as the manifest itself is well formed and declared artifacts exist. Later plans may decide how failed runs affect optimization state.

`started_at_utc` and `completed_at_utc` must use UTC ISO timestamps with `Z` suffix and no microseconds. C-5 validates presence and string shape only; it does not compare clock ordering unless that can be done without introducing a broad datetime policy elsewhere.

`command_label` is descriptive text from the execution agent. It is not executed by Hermes.

## Artifact Path Contract

All result paths in `result_manifest.json` must be project-relative POSIX paths.

These fields are paths:

- `prepared_input_scs`
- `log_file`
- every entry in `artifact_files`

Rules:

- Paths must not be absolute.
- Paths must not contain `..`.
- Paths must stay under `runs/real/<run_id>/`.
- Paths must exist at validation time.
- `prepared_input_scs` must equal the prepared manifest's `rendered_input_scs`.
- `prepared_input_sha256` must equal the prepared manifest's `rendered_input_sha256`.
- The current SHA-256 of `prepared_input_scs` must still equal the prepared manifest's `rendered_input_sha256`.

C-5 does not inspect the contents of `artifact_files`; it only validates existence and path safety.

## Validation Architecture

Add a focused module:

```text
src/hermes_workflow/result_handoff.py
```

Public API:

```python
check_real_run(project_dir: Path, *, run_id: str | None = None) -> RealRunCheckReport
```

`run_id` defaults to `real_001`. If supplied, it must match the same C-4 run ID pattern:

```text
real_[0-9]{3}
```

The implementation should:

1. Validate and load the project bundle with `assert_valid_project(project_dir)`.
2. Resolve `runs/real/<run_id>/`.
3. Load `real_run_manifest.json`.
4. Require prepared manifest `status: "prepared"`.
5. Load `candidate.json`.
6. Load `result_manifest.json`.
7. Validate result manifest schema and allowed status.
8. Verify `run_id` and `candidate_id` match the prepared package.
9. Verify `prepared_input_scs` and `prepared_input_sha256` match the prepared manifest.
10. Re-hash `prepared_input_scs` to confirm it was not changed after C-4.
11. Verify `log_file` and `artifact_files` are safe project-relative paths under the run directory and exist.
12. Write `reports/real_run_check_report.json`.
13. Return the report payload/model.

The validator should always write a report when the project config can be loaded and a run directory can be resolved. If validation fails, the report should have `status: "fail"` and list issues.

If the project config itself cannot be loaded, the CLI may surface the domain error without fabricating a report, following existing CLI patterns.

## Report Contract

Hermes writes:

```text
reports/real_run_check_report.json
```

Successful handoff report:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "run_id": "real_001",
  "candidate_id": "real_001",
  "result_status": "succeeded",
  "real_run_manifest": "runs/real/real_001/real_run_manifest.json",
  "result_manifest": "runs/real/real_001/result_manifest.json",
  "prepared_input_scs": "runs/real/real_001/input.scs",
  "log_file": "runs/real/real_001/spectre.log",
  "artifact_files": [
    "runs/real/real_001/artifacts/psf_summary.txt"
  ],
  "checks": {
    "prepared_manifest_ok": true,
    "candidate_ok": true,
    "result_manifest_ok": true,
    "prepared_input_hash_ok": true,
    "artifact_paths_ok": true
  },
  "issues": []
}
```

Failure report:

```json
{
  "schema_version": "1.0",
  "status": "fail",
  "run_id": "real_001",
  "candidate_id": null,
  "result_status": null,
  "real_run_manifest": "runs/real/real_001/real_run_manifest.json",
  "result_manifest": "runs/real/real_001/result_manifest.json",
  "prepared_input_scs": null,
  "log_file": null,
  "artifact_files": [],
  "checks": {
    "prepared_manifest_ok": false,
    "candidate_ok": false,
    "result_manifest_ok": false,
    "prepared_input_hash_ok": false,
    "artifact_paths_ok": false
  },
  "issues": [
    "result manifest is missing"
  ]
}
```

The report is an inspection artifact. C-5 does not use it to approve metric extraction or optimizer progression; later plans can add those gates.

## CLI Contract

Add:

```bash
hermes-workflow check-real-run PROJECT_DIR
```

Optional run ID:

```bash
hermes-workflow check-real-run PROJECT_DIR --run-id real_001
```

Success output:

```text
real run handoff check passed
run: runs/real/real_001
result: runs/real/real_001/result_manifest.json
report: reports/real_run_check_report.json
```

Failure output:

```text
real run handoff check failed
<issue lines>
report: reports/real_run_check_report.json
```

The command exits with code 1 when the report status is `fail`. Expected domain errors should not print tracebacks.

## Error Handling

Expected issue messages include:

- Missing prepared manifest: `real run manifest is missing`
- Malformed prepared manifest JSON: `real run manifest is invalid`
- Prepared manifest wrong status: `real run package is not prepared`
- Missing candidate file: `candidate file is missing`
- Missing result manifest: `result manifest is missing`
- Malformed result manifest JSON: `result manifest is invalid`
- Wrong result status: `result status is invalid: <value>`
- Run ID mismatch: `result run_id does not match requested run_id`
- Candidate ID mismatch: `result candidate_id does not match prepared candidate`
- Prepared input path mismatch: `result prepared_input_scs does not match prepared manifest`
- Prepared input hash mismatch: `prepared input hash mismatch`
- Unsafe artifact path: `result artifact path is unsafe: <path>`
- Missing artifact path: `result artifact is missing: <path>`

The implementation should collect as many issues as practical in one report once it can load the basic files. It may stop early when a missing or malformed JSON file prevents dependent checks.

## Data Model Placement

Prefer adding report schemas to:

```text
src/hermes_workflow/reports.py
```

Candidate models:

- `RealRunCheckStatus`
- `RealRunResultStatus`
- `RealRunCheckFlags`
- `RealRunCheckReport`

These should follow the existing report model style and use strict values for status fields.

The raw `result_manifest.json` may be validated in `result_handoff.py` with focused helpers or a small Pydantic model. Keep it local unless it becomes shared by later plans.

## Testing

Add tests for:

- Successful `check_real_run()` on sanitized fake artifacts.
- Result status `failed` still producing a pass report when the file contract is valid.
- Missing `result_manifest.json` producing a fail report.
- Malformed `result_manifest.json` producing a fail report.
- Mismatched run ID producing a fail report.
- Mismatched candidate ID producing a fail report.
- Prepared input hash drift producing a fail report.
- Unsafe absolute artifact path producing a fail report.
- Artifact path with `..` producing a fail report.
- Artifact path outside `runs/real/<run_id>/` producing a fail report.
- Missing declared artifact producing a fail report.
- CLI success output.
- CLI failure output without traceback.
- Full selected tests and `ruff check .`.

Tests must use sanitized inline text for logs and artifacts. They must not copy or commit real files from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example`.

## Documentation

Update:

- `README.md`
- `docs/PROJECT_WORKFLOW_OVERVIEW.md`
- `docs/EXECUTION_PROGRESS_2026-05-29.md`
- `docs/COMPACT_RESUME_CHECKPOINT.md`
- `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`

Docs should show the route:

```text
prepare-real-run
execution agent runs Spectre externally
execution agent writes result_manifest.json
check-real-run
future metric extraction
```

Docs must explicitly say C-5 does not run Spectre, parse real metrics, append ledger rows, or start an optimizer loop.

## Security and Safety

C-5 is a contract validator, not a simulator sandbox. It reduces ambiguity by validating returned paths and hashes, but it does not prevent a malicious process from writing files before validation.

Safety guarantees:

- Hermes checks that prepared input did not change after C-4.
- Hermes rejects absolute paths and traversal paths in returned manifests.
- Hermes rejects result artifacts outside the run directory.
- Hermes does not execute command strings from `result_manifest.json`.
- Hermes does not trust chat output from the execution agent.

Remaining external responsibilities:

- The execution environment must restrict where the execution agent can write.
- The real simulator runner must enforce tool-specific safety and license policy.
- Later metric extraction plans must validate simulator output format before consuming data.

## Future Work

Likely follow-up scopes:

- C-6: real metric extraction contract from validated handoff artifacts.
- C-7: single-candidate ledger commit after real metric validation.
- C-8: controlled optimizer loop over real candidate packages.

These should remain separate so C-5 stays a narrow file-contract gate.
