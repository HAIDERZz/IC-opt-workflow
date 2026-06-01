# C-5.5 Dual-Agent Result Handoff Simulation Report

## Summary

C-5.5 simulation gate: passed.

Five controlled scenarios were run against the C-4/C-5 file contracts. The simulated execution-agent role wrote sanitized returned handoff files. The simulated Hermes-observer role judged each scenario only by running `hermes-workflow check-real-run` and reading `reports/real_run_check_report.json`.

All final scenario outcomes matched expectations. The gate found no C-5 product-code bug. It did reveal prompt-level behavior drift in the execution-agent role when the C-5 schema was described loosely, so future real adapters should receive an exact result manifest schema or generated example.

## Repository

- Repository: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`
- Branch: `plan-a-hermes-file-contract-mvp`
- Design spec: `docs/superpowers/specs/2026-06-01-dual-agent-result-handoff-simulation-gate-design.md`
- Implementation plan: `docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md`

## Relevant Commits

- `454ace9 docs: plan dual agent result handoff simulation`
- `929d657 docs: design dual agent result handoff simulation`
- `36a027a docs: record real run result handoff progress`
- `3635dea docs: close real run result handoff contract`
- `9e27775 docs: record dual agent result handoff simulation`

## Scope

Included:

- Prepared a sanitized temporary Hermes project.
- Produced a C-4 first real-run package through the local CLI.
- Used simulated Codex roles for execution-agent and Hermes-observer behavior.
- Covered valid success, valid simulator failure, unsafe path, mutated prepared deck, and candidate identity mismatch.

Excluded:

- No real Spectre run.
- No real Virtuoso run.
- No real Claude CLI execution-agent integration.
- No real Hermes service integration.
- No metric extraction.
- No ledger append.
- No optimizer state write.
- No real `input.scs`, PSF data, proprietary logs, or simulator outputs were committed.

## Temporary Workspace

- Simulation root: `/tmp/c5_5_dual_agent_result_handoff.qTaEcf`
- Base project: `/tmp/c5_5_dual_agent_result_handoff.qTaEcf/base_project`
- Scenario copies:
  - `/tmp/c5_5_dual_agent_result_handoff.qTaEcf/happy_path`
  - `/tmp/c5_5_dual_agent_result_handoff.qTaEcf/valid_failure`
  - `/tmp/c5_5_dual_agent_result_handoff.qTaEcf/unsafe_path`
  - `/tmp/c5_5_dual_agent_result_handoff.qTaEcf/mutated_deck`
  - `/tmp/c5_5_dual_agent_result_handoff.qTaEcf/identity_mismatch`

## Preparation Commands

The controller prepared the sanitized project with the normal local Hermes route:

```bash
hermes-workflow init /tmp/c5_5_dual_agent_result_handoff.qTaEcf/base_project
hermes-workflow validate /tmp/c5_5_dual_agent_result_handoff.qTaEcf/base_project
hermes-workflow package /tmp/c5_5_dual_agent_result_handoff.qTaEcf/base_project
hermes-workflow prepare-netlist /tmp/c5_5_dual_agent_result_handoff.qTaEcf/base_project
hermes-workflow dry-run /tmp/c5_5_dual_agent_result_handoff.qTaEcf/base_project
hermes-workflow preflight-health /tmp/c5_5_dual_agent_result_handoff.qTaEcf/base_project
hermes-workflow approve /tmp/c5_5_dual_agent_result_handoff.qTaEcf/base_project
hermes-workflow prepare-real-run /tmp/c5_5_dual_agent_result_handoff.qTaEcf/base_project
```

Observed successful outputs included:

- `validation passed`
- `execution_package/execution_manifest.json`
- `netlist preparation passed`
- `dry run passed`
- `preflight health passed`
- `approve_first_real_run`
- `real run package prepared`
- `run: runs/real/real_001`
- `manifest: runs/real/real_001/real_run_manifest.json`

The base project had no `runs/real/real_001/result_manifest.json` before the scenario copies were created.

## Role Prompt Summary

Execution-agent role:

- Could read the prepared `input.scs`, `candidate.json`, and `real_run_manifest.json`.
- Could write sanitized fake `spectre.log`, sanitized artifacts under `runs/real/real_001/artifacts/`, and `result_manifest.json`.
- Could intentionally violate the contract only for the negative scenario being tested.
- Could not run Spectre, Virtuoso, simulator commands, license tools, metric extraction, ledger writes, or optimizer writes.

Hermes-observer role:

- Could run only `hermes-workflow check-real-run PROJECT_DIR`.
- Could read only `reports/real_run_check_report.json` for the verdict.
- Could not trust execution-agent prose, repair files, run tools, extract metrics, append ledger rows, or write optimizer state.

The full shared role prompt fragments are preserved in `docs/superpowers/plans/2026-06-01-dual-agent-result-handoff-simulation-gate.md`. During retries, the execution-agent prompts were tightened to enumerate the exact C-5 result manifest fields and status enum values.

## Role Dispatch Evidence

The simulation used separate subagents for execution-agent and Hermes-observer responsibilities. The controller did not use execution-agent prose as the verdict; observer results came from `check-real-run` and `reports/real_run_check_report.json`.

| Scenario | Execution-Agent Role | Hermes-Observer Role |
| --- | --- | --- |
| `happy_path` | First: `Ramanujan` (`019e81f4-698d-7cb3-b01e-deeb83692c87`); retry: `Parfit` (`019e81f6-c7be-7223-8646-a2e2ca871ba5`) | First: `Lovelace` (`019e81f5-d24b-7ed2-b356-ff8a64d2976c`); retry: `Hume` (`019e81f8-0d27-7aa2-a879-65e42147fd2f`) |
| `valid_failure` | `Peirce` (`019e81f4-97e7-7bd3-b22d-0e701d94cb79`) | `Gauss` (`019e81f5-f7dd-7211-af89-74f9bd383a5c`) |
| `unsafe_path` | First: `Fermat` (`019e81f9-0ce2-7611-badb-fa6876caf567`); retry: `Nietzsche` (`019e81fb-c3cd-7cb0-8e9c-077ebf95b994`) | First: `Darwin` (`019e81fa-648c-7c71-b13f-b152580cfd8a`); retry: `Aquinas` (`019e81fe-3429-7012-9c02-fed9e1419d99`) |
| `mutated_deck` | First: `Mencius` (`019e81f9-3b1e-7d21-8bb1-1c57f054446a`); retry: `Kuhn` (`019e81fc-023d-7291-b782-f9033dc7b47c`) | First: `Aristotle` (`019e81fa-8f2f-7e93-873c-790486297955`); retry: `Mill` (`019e81fe-52a5-74d0-9381-e57928a6ee7c`) |
| `identity_mismatch` | First: `Dalton` (`019e81f9-6b1a-7f01-ad3f-63f47f50d12a`); retry: `Galileo` (`019e81fe-10ba-7472-bdc3-7faadd457da6`) | First: `Beauvoir` (`019e81fa-b553-70d0-9e19-77239cb8134f`); retry: `Godel` (`019e81ff-e066-72a1-a883-b0d219e9a050`) |

## Structured Role Outputs

Final execution-agent outputs:

- `happy_path`: `STATUS: DONE`; wrote `runs/real/real_001/result_manifest.json`, `runs/real/real_001/spectre.log`, and `runs/real/real_001/artifacts/psf_summary.txt`.
- `valid_failure`: `STATUS: DONE`; wrote `runs/real/real_001/result_manifest.json`, `runs/real/real_001/spectre.log`, and `runs/real/real_001/artifacts/psf_summary.txt`.
- `unsafe_path`: `STATUS: DONE`; wrote `runs/real/real_001/result_manifest.json`, `runs/real/real_001/spectre.log`, and `runs/real/real_001/artifacts/psf_summary.txt`; did not create `/tmp/c5_5_outside_spectre.log`.
- `mutated_deck`: `STATUS: DONE`; wrote `runs/real/real_001/result_manifest.json`, `runs/real/real_001/spectre.log`, `runs/real/real_001/artifacts/psf_summary.txt`, and mutated `runs/real/real_001/input.scs`.
- `identity_mismatch`: `STATUS: DONE`; wrote `runs/real/real_001/result_manifest.json`, `runs/real/real_001/spectre.log`, and `runs/real/real_001/artifacts/psf_summary.txt`.

Final Hermes-observer outputs:

- `happy_path`: `CHECK_EXIT_CODE: 0`; `REPORT_STATUS: pass`; `RESULT_STATUS: succeeded`; `ISSUES: []`; `MATCHED_EXPECTATION: yes`.
- `valid_failure`: `CHECK_EXIT_CODE: 0`; `REPORT_STATUS: pass`; `RESULT_STATUS: failed`; `ISSUES: []`; `MATCHED_EXPECTATION: yes`.
- `unsafe_path`: `CHECK_EXIT_CODE: 1`; `REPORT_STATUS: fail`; `RESULT_STATUS: succeeded`; `ISSUES: ["result artifact path is unsafe: /tmp/c5_5_outside_spectre.log"]`; `MATCHED_EXPECTATION: yes`.
- `mutated_deck`: `CHECK_EXIT_CODE: 1`; `REPORT_STATUS: fail`; `RESULT_STATUS: succeeded`; `ISSUES: ["prepared input hash mismatch"]`; `MATCHED_EXPECTATION: yes`.
- `identity_mismatch`: `CHECK_EXIT_CODE: 1`; `REPORT_STATUS: fail`; `RESULT_STATUS: succeeded`; `ISSUES: ["result candidate_id does not match prepared candidate", "result candidate_id does not match candidate file"]`; `MATCHED_EXPECTATION: yes`.

## Scenario Results

| Scenario | Expected | Observed Exit | Report Status | Issues | Assessment |
| --- | --- | --- | --- | --- | --- |
| `happy_path` | Valid `succeeded` handoff passes | 0 | `pass`, `result_status: succeeded` | `[]` | Passed after prompt tightening |
| `valid_failure` | Valid `failed` handoff passes | 0 | `pass`, `result_status: failed` | `[]` | Passed |
| `unsafe_path` | Absolute result path rejected | 1 | `fail`, `result_status: succeeded` | `result artifact path is unsafe: /tmp/c5_5_outside_spectre.log` | Passed after prompt tightening |
| `mutated_deck` | Post-prepare `input.scs` mutation rejected | 1 | `fail`, `result_status: succeeded` | `prepared input hash mismatch` | Passed after prompt tightening |
| `identity_mismatch` | Wrong `candidate_id` rejected | 1 | `fail`, `result_status: succeeded` | `result candidate_id does not match prepared candidate`; `result candidate_id does not match candidate file` | Passed after prompt tightening |

## Scenario Notes

### happy_path

The first execution-agent attempt wrote `created_at_utc` instead of the required `started_at_utc`, so `check-real-run` rejected the result manifest as invalid. After the prompt enumerated the exact C-5 fields, the execution-agent wrote a valid `status: "succeeded"` handoff. The observer reported exit code `0`, report status `pass`, result status `succeeded`, and no issues.

### valid_failure

The execution-agent wrote a structurally valid returned handoff with `status: "failed"`. The observer reported exit code `0`, report status `pass`, result status `failed`, and no issues. This confirms that simulator failure is treated as a valid returned result, not as a file-contract failure.

### unsafe_path

The first execution-agent attempt mixed in an older simulator object shape, so the manifest failed before the intended unsafe-path check. After prompt tightening, the execution-agent wrote the exact C-5 shape and set `log_file` to `/tmp/c5_5_outside_spectre.log`. The observer reported exit code `1`, report status `fail`, result status `succeeded`, and issue `result artifact path is unsafe: /tmp/c5_5_outside_spectre.log`.

The outside file `/tmp/c5_5_outside_spectre.log` was not created.

### mutated_deck

The first execution-agent attempt used an invalid status value from an older contract shape. After prompt tightening, the execution-agent wrote an otherwise valid manifest and left exactly one simulated post-prepare mutation line in `runs/real/real_001/input.scs`. The observer reported exit code `1`, report status `fail`, result status `succeeded`, and issue `prepared input hash mismatch`.

### identity_mismatch

The first execution-agent attempt used an invalid status value from an older contract shape. After prompt tightening, the execution-agent wrote an otherwise valid manifest with `candidate_id: "wrong_candidate"`. The observer reported exit code `1`, report status `fail`, result status `succeeded`, and issues `result candidate_id does not match prepared candidate` and `result candidate_id does not match candidate file`.

## Behavior Findings

- The Hermes-observer role behaved correctly: it did not trust execution-agent prose and used only the CLI exit code plus `reports/real_run_check_report.json`.
- The C-5 checker failed closed on malformed result manifests before deeper semantic checks.
- The execution-agent role drifted toward older C-4/C-5-adjacent shapes when prompts were underspecified, especially timestamp fields, simulator fields, and result status enums. Four of five scenarios needed prompt tightening before the intended file-contract scenario was isolated.
- Exact schema enumeration in the execution-agent prompt was enough to produce the intended handoff shape across all retry scenarios.
- The deterministic file contract successfully constrained unsafe behavior without needing real Spectre, Virtuoso, metric extraction, or optimizer integration.

## C-5 Bugs Discovered

None.

The rejection cases were blocked by existing C-5 checks:

- Unsafe result path detection.
- Prepared input SHA-256 drift detection.
- Candidate identity consistency checks.
- Strict result manifest schema validation.

## Deferred Minor Improvements

- Add a small generated or documented valid `result_manifest.json` example for future execution-agent prompts. This should be carried into C-6 planning before real adapter work starts.
- Consider adding a machine-readable JSON Schema for the returned result manifest if real adapters show repeated schema drift.
- Consider documenting that a valid simulator failure should use `status: "failed"` and still pass the file-contract check.

## Next Recommended Scope

Confirm Plan C-6 real metric result contract scope before adding real metric extraction, ledger append, optimizer state writes, or physical Spectre/Virtuoso adapters.

C-6 planning should explicitly decide whether C-6.5 remains a separate dual-agent metric extraction simulation gate after the real metric result contract is designed.
