# Local Real-Run Smoke Design

Date: 2026-06-03

## Goal

Add C-11 as a local, fake-controlled smoke gate that proves the real-run workflow can advance through the existing file contracts without invoking real tools.

C-11 validates two end-to-end contract paths:

```text
happy path:
C-9 prepare-next-real-run
-> fake C-7 execution-side artifacts
-> check-real-run
-> check-metric-results
-> C-8 record-real-result

controlled failure/retry path:
C-9 prepare-next-real-run
-> fake failed or partial C-7 artifacts
-> C-10 recovery assessment
-> explicit retry decision
-> C-10 prepare-real-run-retry
-> fake C-7 success artifacts for retry
-> check-real-run
-> check-metric-results
-> C-8 record-real-result
```

The smoke exists to catch integration regressions between already-built contracts before the project moves into real Virtuoso/Spectre/OCEAN/agent practice.

## Locked Role Model

C-11 follows `docs/ROLE_MODEL_AND_TERMINOLOGY.md`.

- The supervisor agent drives the workflow by calling Hermes workflow commands and reading reports.
- Hermes workflow tooling validates, packages, records, classifies, and prepares retry packages.
- The execution agent is represented by deterministic fake files in C-11. Real execution-agent behavior is deferred.

C-11 must not describe Hermes as an autonomous supervisor agent. In this project, Hermes means the deterministic workflow tooling layer.

## Background

Plan C now has the individual pieces needed for a first closed-loop rehearsal:

- C-7 can run through an execution-side adapter boundary, but its tested behavior is fake-runner based.
- C-8 can record checked real metric results into ledger and optimizer state.
- C-9 can prepare the next real-run package after checked results exist.
- C-10 can classify unresolved runs, force explicit supervisor recovery decisions, and prepare retry packages.

Those pieces have each passed focused review gates. The remaining local risk is orchestration drift: a later command may emit valid output in isolation but leave the next command unable to continue. C-11 tests the chain as one local workflow while preserving the no-real-tool boundary.

## Scope

Included:

- Add a local smoke command or test helper that exercises the C-9 -> C-7-fake-artifacts -> C-5/C-6 -> C-8 path.
- Add a controlled failure/retry smoke that exercises C-10 before recording a retry success.
- Use committed synthetic fixtures only.
- Use deterministic fake result manifests and metric result manifests that satisfy the existing C-5/C-6 contracts.
- Assert ledger, optimizer state, best-candidate state, recovery reports, and retry package metadata after each stage.
- Produce a concise smoke report or test output that is useful for handoff.

Excluded:

- Running Virtuoso, Spectre, OCEAN, SSH, Claude CLI, `virtuoso-bridge-lite`, or network access.
- Calling a real execution agent.
- Running the C-7 adapter with subprocess-backed real commands.
- Reading or committing local proprietary `input.scs`, PSF, Maestro, or Cadence evidence files.
- Parsing PSF or waveform databases in Python.
- Rewriting, translating, discovering, or reimplementing OCEAN/Calculator formulas.
- Adding optimizer model policy, batch scheduling, multi-corner handling, or failure-penalty ledger rows.

## Design Options Considered

### Option A: Local/Fake Controlled Smoke

Use synthetic project fixtures and fake C-7 returned artifacts to exercise the complete workflow contract. The smoke can run in normal CI and does not require a Cadence environment.

This is the chosen design. It gives fast regression coverage and protects the project from mixing contract bugs with tool-environment bugs.

### Option B: Real Local Cadence Smoke

Use the verified local Virtuoso/Spectre/OCEAN environment and real known cells to run C-11. This would provide stronger physical evidence, but it would make this step dependent on licenses, host state, local evidence files, and runtime stability.

This is deferred until after C-11 proves the contract chain locally.

### Option C: Real Dual-Agent Smoke

Use a supervisor agent and a tool-side execution agent to run the whole loop through real agent boundaries. This is closest to production behavior, but it adds too many variables before the file contracts have a local closed-loop gate.

This is deferred to a later real-tool/agent integration plan.

## Local/Fake Boundary

C-11 may use fake files that model C-7 outputs, but those files must still pass the same validators used for real returned artifacts.

Allowed fake artifacts:

- `runs/real/<run_id>/result_manifest.json`
- `runs/real/<run_id>/metric_result_manifest.json`
- synthetic log files declared in the result manifest
- synthetic PSF/metric artifact directories when required only as path-presence evidence

The fake artifacts must be ordinary project-relative files under the test project directory. They must not be symlinks, absolute paths, or references outside the fixture project.

C-11 must not bypass:

- `check-real-run`
- `check-metric-results`
- `record-real-result`
- C-10 unresolved-run guard
- C-10 recovery decision requirements

## Happy Path Smoke

The happy path starts from a fixture project with:

- valid configs
- approved package state
- at least one previously recorded real result
- optimizer state ready for C-9 to select the next initialization candidate

The smoke then:

1. Calls `prepare-next-real-run` for the next candidate.
2. Writes fake successful result and metric manifests for that run.
3. Runs `check-real-run`.
4. Runs `check-metric-results`.
5. Runs `record-real-result`.
6. Verifies that the ledger contains the new run exactly once.
7. Verifies that optimizer state and best-candidate state are derived from checked metric results.
8. Verifies that a subsequent unresolved-run guard no longer blocks on the recorded run.

## Controlled Failure/Retry Smoke

The failure/retry path starts from the same class of fixture project and then:

1. Calls `prepare-next-real-run`.
2. Writes a fake failed or partial result state.
3. Runs `assess-real-run-recovery` and expects a retry-capable classification.
4. Verifies that C-9 is blocked while the failed run is unresolved.
5. Writes an explicit supervisor retry decision.
6. Calls `prepare-real-run-retry`.
7. Verifies that the retry package preserves the same candidate identity and parameters while using a new `real_###` run id.
8. Writes fake successful result and metric manifests for the retry run.
9. Runs `check-real-run`, `check-metric-results`, and `record-real-result` for the retry run.
10. Verifies that the original failed run is resolved by the recorded retry and no longer blocks C-9.

The smoke should prefer the smallest failure mode that exercises the C-10 path. A partial or failed returned manifest is enough; C-11 should not invent new recovery states.

## Fixture Strategy

C-11 should reuse existing fixture builders where they are already clear and stable. If reuse would make the smoke hard to read, the implementation plan may add a small focused test helper under `tests/` that creates:

- a valid template project
- an approved first real-run package
- one checked/recorded seed real result
- deterministic fake C-7 result artifacts

The helper must remain test-only. It must not become production API or a broad fixture framework.

## CLI And Library Coverage

C-11 should include library-level coverage for precise assertions and at least one CLI-level smoke if it adds meaningful signal without duplicating the whole scenario.

Library-level checks are primary because they can assert intermediate state directly. CLI-level checks are useful for confirming command wiring and supervisor-facing output.

The implementation plan should keep the CLI smoke narrow. It should not turn C-11 into a second end-to-end test suite for every command.

## Reports And Evidence

C-11 should leave machine-readable evidence in the fixture project during tests:

- real-run manifests
- metric result manifests
- `reports/real_run_check_report.json`
- `reports/metric_result_check_report.json`
- `reports/real_result_record_report.json`
- `reports/real_run_recovery_report.json`
- retry `recovery_decision.json`
- ledger and optimizer state files

The committed evidence should be source fixtures and tests only. Runtime-generated smoke output should remain under pytest temporary directories or a controlled ignored location.

## Failure Handling

C-11 should fail closed when:

- fake C-7 artifacts are incomplete or unsafe
- `check-real-run` does not pass before metric checking
- `check-metric-results` does not pass before recording
- C-9 can advance while a failed run is unresolved
- retry package generation changes candidate parameters
- retry package generation overwrites failed-run evidence
- a run is recorded twice
- a recovery decision is missing for retry preparation

These failures should surface through existing exceptions, reports, and CLI exit behavior. C-11 should not add a parallel failure language.

## Acceptance Criteria

C-11 is acceptable when:

- happy path smoke proves `prepare-next-real-run -> check-real-run -> check-metric-results -> record-real-result`
- controlled failure/retry smoke proves `assess-real-run-recovery -> prepare-real-run-retry -> record retry success`
- the C-10 unresolved-run guard is exercised before and after retry resolution
- all smoke artifacts are synthetic and project-relative
- no real tool, network, SSH, bridge, or execution-agent invocation is performed
- no PSF parsing or formula rewriting is introduced
- full local tests and ruff pass
- spec and code-quality review gates pass before moving to real-tool practice

## Next Scope After C-11

After C-11 passes, the next recommended scope is a deliberately separate real-tool/agent practice plan.

That later plan may use the previously validated local Virtuoso/Spectre/OCEAN environment and known cells, but it should start from a clean decision point:

```text
C-11 local/fake smoke passed
-> choose real local Cadence smoke OR real dual-agent smoke
-> run only approved real-tool commands
-> keep proprietary artifacts local unless explicitly approved for commit
```

C-11 does not itself authorize direct real tool or real agent integration.
