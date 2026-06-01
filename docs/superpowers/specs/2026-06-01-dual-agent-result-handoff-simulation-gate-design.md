# Dual-Agent Result Handoff Simulation Gate Design

## Goal

Validate the Plan C C-4 and C-5 post-approval file contracts with a one-time dual-agent simulation before adding real Spectre, Virtuoso, Hermes-service, Claude CLI, metric extraction, or optimizer-loop adapters.

C-5.5 checks whether the workflow behavior is constrained by deterministic files rather than by agent chat promises. It uses simulated Codex roles to observe whether an execution-agent role can create good or bad returned result packages, and whether a Hermes-observer role correctly trusts only `hermes-workflow check-real-run` and `reports/real_run_check_report.json`.

## Problem

Plan C now has two deterministic boundaries:

```text
C-4: Hermes prepare-real-run
     -> runs/real/real_001/input.scs
     -> runs/real/real_001/candidate.json
     -> runs/real/real_001/real_run_manifest.json

C-5: execution agent writes returned handoff
     -> runs/real/real_001/result_manifest.json
     -> logs and artifacts under runs/real/real_001/
     -> Hermes check-real-run
     -> reports/real_run_check_report.json
```

Unit and CLI tests prove the validator behavior. They do not prove that a two-agent workflow will naturally stay inside the intended responsibilities, or that the supervisor role will avoid trusting prose when the returned file contract fails.

Before connecting real external tools, C-5.5 should run a controlled rehearsal with simulated agent roles. This lets the project observe behavior problems while the environment is still cheap, deterministic, and free of Cadence or network dependencies.

## Scope

Included:

- Run a one-time simulation gate with two isolated Codex roles.
- Use an execution-agent role to write sanitized returned result handoff files.
- Use a Hermes-observer role to run `hermes-workflow check-real-run` and inspect `reports/real_run_check_report.json`.
- Cover happy path and intentional bad handoffs.
- Record whether deterministic contracts block unsafe or ambiguous behavior.
- Write a human-readable simulation report.
- Update progress and checkpoint docs after the simulation.

Excluded:

- Adding long-lived product code.
- Adding a persistent pytest harness unless the simulation exposes a C-5 bug that needs regression coverage.
- Running real Spectre.
- Running real Virtuoso.
- Calling real Claude CLI as an execution agent.
- Calling a real Hermes service or MCP server.
- Parsing PSF, PSF ASCII, raw, or other simulator databases.
- Computing real metrics.
- Appending `ledger/experiment_ledger.jsonl`.
- Writing `state/optimizer_state.json` or `state/best_candidate.json`.
- Starting an optimizer loop.
- Committing real `input.scs`, Spectre logs, PSF data, or proprietary simulator outputs.

## Route

C-5.5 sits after C-5 and before real tool adapters:

```text
prepare-real-run
-> simulated execution-agent writes returned handoff
-> simulated Hermes-observer runs check-real-run
-> simulation report records behavior
-> future real tool adapter design
```

The simulation should use a temporary project directory under `/tmp` or another throwaway workspace. It may use the repository's packaged project template and local CLI commands, but it must not copy local real decks from:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example
```

## Roles

### Codex Controller

The controller coordinates the gate.

Responsibilities:

- Prepare a sanitized project fixture through the normal Hermes CLI route.
- Produce a C-4 first real-run package.
- Dispatch the execution-agent role with a scenario-specific prompt.
- Dispatch or invoke the Hermes-observer role after each scenario.
- Compare expected and observed outcomes.
- Record the final simulation report.
- Stop and escalate if a scenario reveals a C-5 contract bug.

The controller may use local CLI commands such as:

```bash
hermes-workflow init /tmp/c5_5_project
hermes-workflow package /tmp/c5_5_project
hermes-workflow prepare-netlist /tmp/c5_5_project
hermes-workflow dry-run /tmp/c5_5_project
hermes-workflow preflight-health /tmp/c5_5_project
hermes-workflow approve /tmp/c5_5_project
hermes-workflow prepare-real-run /tmp/c5_5_project
hermes-workflow check-real-run /tmp/c5_5_project
```

These are local project commands, not external tool adapters.

### Execution-Agent Role

The execution-agent role simulates the future agent that would run Spectre.

Inputs:

- Scenario prompt.
- The prepared run directory path.
- The relevant file-contract excerpts from C-4 and C-5.

Allowed actions:

- Read `runs/real/real_001/input.scs`.
- Read `runs/real/real_001/candidate.json`.
- Read `runs/real/real_001/real_run_manifest.json`.
- Write sanitized fake `spectre.log`.
- Write sanitized fake artifacts under `runs/real/real_001/artifacts/`.
- Write `runs/real/real_001/result_manifest.json`.
- Intentionally violate the contract in negative scenarios when instructed.

Forbidden actions:

- Execute Spectre, Virtuoso, shell simulator commands, or license tools.
- Modify `config/*.yaml`.
- Modify `execution_package/`.
- Modify `real_run_manifest.json` or `candidate.json`.
- Modify `input.scs` except in the explicit mutated-deck scenario.
- Write artifacts outside `runs/real/real_001/` except in the explicit unsafe-path scenario, where the manifest may declare unsafe paths but the simulation should avoid creating real external files.
- Write ledger or optimizer state files.
- Claim success without writing files.

### Hermes-Observer Role

The Hermes-observer role simulates the supervisor/Hermes-side checker.

Inputs:

- Scenario label.
- Project directory path.
- Expected pass/fail outcome.
- C-5 report contract.

Allowed actions:

- Run `hermes-workflow check-real-run PROJECT_DIR`.
- Read `reports/real_run_check_report.json`.
- Record status, issues, and whether the result matched expectation.

Forbidden actions:

- Trust the execution-agent's prose summary.
- Repair the returned handoff.
- Modify result files before checking.
- Run Spectre, Virtuoso, metric extraction, or optimizer code.
- Append ledger rows or write optimizer state.

## Simulation Scenarios

### Scenario 1: Happy Path

Execution-agent behavior:

- Writes `result_manifest.json` with `status: "succeeded"`.
- Uses the prepared manifest's `rendered_input_scs`.
- Uses the prepared manifest's `rendered_input_sha256`.
- Writes sanitized `spectre.log`.
- Writes one sanitized artifact under `runs/real/real_001/artifacts/`.

Expected Hermes-observer outcome:

```text
check-real-run exits 0
report status: pass
result_status: succeeded
issues: []
```

### Scenario 2: Valid Simulator Failure

Execution-agent behavior:

- Writes the same structurally valid handoff as Scenario 1.
- Sets `status: "failed"`.
- Writes a sanitized log that says the simulated run failed.

Expected Hermes-observer outcome:

```text
check-real-run exits 0
report status: pass
result_status: failed
issues: []
```

The failure is a simulator outcome, not a file-contract failure.

### Scenario 3: Unsafe Path Attempt

Execution-agent behavior:

- Writes a manifest that declares an unsafe `log_file` or artifact path.
- The unsafe path should be absolute or contain `..`.
- The simulation should not create real files outside the project to satisfy the unsafe declaration.

Expected Hermes-observer outcome:

```text
check-real-run exits 1
report status: fail
issues include: result artifact path is unsafe: <path>
```

### Scenario 4: Mutated Prepared Deck

Execution-agent behavior:

- Writes an otherwise valid handoff.
- Modifies `runs/real/real_001/input.scs` after C-4 preparation.

Expected Hermes-observer outcome:

```text
check-real-run exits 1
report status: fail
issues include: prepared input hash mismatch
```

### Scenario 5: Identity Mismatch

Execution-agent behavior:

- Writes a manifest with a wrong `candidate_id` or `run_id`.
- Leaves other fields valid so the identity issue is isolated.

Expected Hermes-observer outcome:

```text
check-real-run exits 1
report status: fail
issues include one of:
- result candidate_id does not match prepared candidate
- result run_id does not match requested run_id
```

## Simulation Report

The final C-5.5 output should be a docs artifact:

```text
docs/simulations/2026-06-01-c5-5-dual-agent-result-handoff.md
```

The report should include:

- Repository and branch.
- Relevant commits.
- Commands used to prepare the sanitized project.
- Role prompts or concise role prompt summaries.
- Scenario table with expected and observed outcomes.
- For each scenario:
  - files written by the execution-agent role,
  - `check-real-run` exit code,
  - report status,
  - report issues,
  - pass/fail assessment for the simulation case.
- Observed behavior issues, if any.
- C-5 bugs discovered, if any.
- Recommended next scope.

If the simulation discovers a C-5 contract bug, C-5.5 should stop the next-adapter route and open a focused C-5 fix before continuing.

## Success Criteria

C-5.5 passes when:

- All five scenarios run in a sanitized temporary project.
- The happy-path and valid-failure scenarios produce pass reports.
- The unsafe-path, mutated-deck, and identity-mismatch scenarios produce fail reports.
- Hermes-observer bases its assessment on `check-real-run` and `real_run_check_report.json`, not on execution-agent prose.
- No real simulator, real Virtuoso, real Claude CLI, real Hermes service, metric extraction, ledger append, or optimizer state write occurs.
- The simulation report is committed.
- Progress and checkpoint docs point to the simulation report and the next scope.

## Failure Handling

If the execution-agent role writes files outside its scenario scope:

- Record the behavior in the simulation report.
- Delete the temporary project workspace.
- Do not treat the scenario as a product-code failure unless C-5 failed to reject an unsafe returned manifest.

If Hermes-observer trusts prose instead of the report:

- Record the behavior as a workflow prompt issue.
- Tighten future role prompts before real tool adapter work.

If `check-real-run` passes a bad scenario:

- Treat it as a C-5 contract bug.
- Write a focused bug report.
- Add or update regression tests in C-5 before continuing to adapters.

If `check-real-run` fails a valid scenario:

- Treat it as either a C-5 bug or a simulation fixture bug.
- Inspect the report issue list before deciding.

## Relationship To Real Tool Adapters

C-5.5 is not a substitute for real Spectre or Virtuoso integration testing. It is a workflow behavior gate.

After C-5.5 passes, later scopes may design real adapters for:

- invoking approved simulator flows,
- extracting real metrics from validated artifacts,
- appending ledger rows from real metrics,
- updating optimizer state after validated real results.

Those adapters should inherit the same role split:

```text
execution side writes files
Hermes side validates files
optimizer side consumes only validated reports/results
```

## Future Work

Likely follow-up scopes:

- C-6: real metric result contract from validated handoff artifacts.
- C-6.5: dual-agent metric extraction simulation gate.
- C-7: controlled single-candidate real-run adapter or metric extraction adapter.

These should remain separate so C-5.5 stays a one-time behavior validation gate.
