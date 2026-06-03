# Narrow Optimizer Loop Productization Design

Date: 2026-06-04

## Purpose

C-14 proved the minimum real-tool path:

```text
suggest-candidate
-> prepare-candidate-real-run
-> C-7 Spectre/OCEAN adapter
-> check-real-run
-> check-metric-results
-> record-real-result
```

C-15 productizes only that proven path into a small loop driver. It must not become a broad optimizer framework.

The loop exists so a supervisor agent can ask Hermes workflow tooling and the execution-side adapter to evaluate a small number of additional candidates without hand-typing each command.

## Ground Rules

- Preserve the native Maestro/ADE/Spectre/OCEAN netlist layout.
- Reuse existing contracts:
  - `suggest-candidate`
  - `prepare-candidate-real-run`
  - C-7 Spectre/OCEAN adapter
  - `check-real-run`
  - `check-metric-results`
  - `record-real-result`
- Python must not parse PSF data.
- Python must not translate or rewrite OCEAN formulas.
- Failed real-tool handoffs must fail closed.
- Candidate metric failures must be visible, not silently hidden as success.
- Real Spectre/OCEAN execution must run outside the Codex sandbox in this environment because Spectre needs pipe/socket creation.

## Scope

Add one narrow loop entry point that can run a fixed number of candidate cycles against an already prepared and approved project.

The MVP loop should:

1. Read the current ledger and optimizer state.
2. Allocate the next candidate id and real-run id deterministically.
3. Ask the existing suggestion contract for one candidate.
4. Prepare one candidate real-run package.
5. Invoke the existing C-7 adapter for that run.
6. Run existing result and metric checks.
7. Record the result when checks pass.
8. Stop when the requested new-evaluation budget is reached or when a fail-closed condition appears.

## Non-Goals

- No new optimizer algorithm.
- No new TuRBO implementation.
- No daemon, service, queue, or scheduler.
- No parallel batch execution.
- No automatic Virtuoso/Maestro netlist export.
- No raw Cadence artifact commit.
- No broad retry policy beyond existing C-10/C-7 behavior.
- No penalty model for non-scalar metric failures in this MVP unless existing contracts already support it.

## Proposed Interface

Use a repo tool rather than a core Hermes CLI command for the first productization pass:

```bash
tools/run_real_optimizer_loop.py PROJECT_DIR \
  --max-new-evaluations 1 \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

Reasons:

- It is explicitly execution-side orchestration, not a new Hermes core contract.
- It can launch the C-7 adapter through the approved Cadence shell path.
- It keeps real-tool behavior isolated from contract-only commands.

The command should print one compact line per cycle and write a sanitized summary under the project `reports/` directory. Raw Spectre/OCEAN artifacts remain inside `runs/real/<run_id>/` and are not copied into the repository.

## ID Allocation

The loop should allocate:

- `candidate_00000N` from existing `candidate_requests/` plus checked ledger rows.
- `real_00N` from existing `runs/real/` directories.

It must refuse to overwrite an existing candidate request or real-run directory.

For C-15 MVP, id allocation can be conservative and deterministic. It does not need a separate database.

## Failure Handling

Each cycle has these states:

- `recorded`: adapter, checks, and record all passed.
- `adapter_failed`: C-7 adapter failed or did not write the required manifests.
- `result_check_failed`: `check-real-run` failed.
- `metric_check_failed`: `check-metric-results` failed.
- `record_failed`: result passed checks but `record-real-result` failed.

On any non-`recorded` state, the loop stops and reports the failing run id. It should not edit returned manifests by hand.

## Acceptance Criteria

C-15 is accepted when:

- A fake-adapter test proves the loop can record at least one candidate cycle without real tools.
- A local C-14 project can run one additional real candidate cycle through the real C-7 adapter.
- The loop preserves native netlist sidecars and approved OCEAN formulas.
- The loop leaves raw Cadence artifacts local-only.
- The implementation remains small and scoped to the proven path.

C-15 is rejected or narrowed if:

- It requires Python PSF parsing.
- It requires formula rewriting.
- It introduces a broad framework, daemon, or scheduler.
- It cannot clearly distinguish adapter, result-check, metric-check, and record failures.
