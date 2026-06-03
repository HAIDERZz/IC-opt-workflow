# Controlled Real-Tool/Agent Practice Design

Date: 2026-06-03

## Goal

Add C-12 as the first deliberately scoped real-tool/agent practice gate after the C-11 local/fake controlled smoke.

C-12 should prove that the already-built file contracts can drive one real Cadence execution round without route drift:

```text
Hermes workflow tooling prepares an approved real-run package
-> execution agent runs the C-7 Spectre + OCEAN adapter on that package
-> adapter writes returned real-run and metric artifacts
-> Hermes workflow tooling checks and records the result
-> supervisor agent reads machine-readable reports and decides the next scope
```

C-12 is an evidence gate, not a production optimizer loop.

## Locked Role Model

C-12 follows `docs/ROLE_MODEL_AND_TERMINOLOGY.md`.

- The supervisor agent plans the practice, approves the run, reads reports, and decides whether to proceed or stop.
- Hermes workflow tooling owns deterministic file contracts, preflight, approval, real-run package preparation, handoff checks, metric result checks, recovery checks, ledger/state recording, and reports.
- The execution agent owns real tool execution after an approved package exists. It may be a tool-side agent, scripted worker, or explicitly labeled manual/operator action.

Do not describe Hermes as a local LLM supervisor agent. In this project, Hermes means workflow tooling.

If the same human/operator session triggers a tool command during C-12, the evidence must still label that phase as execution-agent/tool-side action. The supervisor role must not silently become the physical simulator runner.

## Background

The project now has the contract layers needed for one controlled real practice:

- C-4 prepares post-approval real-run packages.
- C-5 validates returned `result_manifest.json`.
- C-6 validates returned OCEAN metric result artifacts and exact approved formula identity.
- C-7 provides the execution-side Spectre + OCEAN adapter and has fake-runner test coverage.
- C-8 records checked real metric results into ledger/state.
- C-9 prepares next real-run packages after checked results exist.
- C-10 blocks unresolved real runs and provides recovery/retry contracts.
- C-11 proved the C-9 -> fake C-7-style artifacts -> C-5/C-6 -> C-8 happy path and one C-10 retry path locally.

The remaining risk is not schema design. The remaining risk is whether a real execution-agent/tool-side pass can produce artifacts that the deterministic contracts accept without ad-hoc interpretation, formula rewriting, or PSF parsing.

## Chosen Scope

C-12 should start with the smallest useful real practice:

```text
one known cell
one project directory
one approved real-run package
one Spectre run
one batch OCEAN metric extraction
one Hermes check/record pass
```

Recommended first cell:

```text
Virtuoso_Bridge_test/bridge_test_inv
```

This cell has already been used in earlier Spectre/OCEAN evidence work and is simpler than the PSS/PAC mixer path. PSS/PAC practice can follow only after the first C-12 inverter-style path is stable.

## Design Options Considered

### Option A: Contract-Led Single Real Run

Use the existing Hermes commands to prepare one approved package, then have the execution agent run the existing C-7 adapter, then use existing Hermes checks and recording commands.

This is the chosen design. It gives the strongest evidence that the actual workflow boundary works while keeping the blast radius small.

### Option B: Direct Tool Smoke Outside Hermes Contracts

Run Spectre and OCEAN manually, then inspect outputs by hand. This is useful as lab evidence, but it does not prove the project workflow. It also increases the chance that chat prose or visual inspection replaces machine-readable reports.

This option is rejected for C-12.

### Option C: Full Autonomous Dual-Agent Optimization Loop

Let a supervisor agent and execution agent run multiple candidates with real tools. This is closest to the eventual goal, but it mixes too many variables before a single approved real-run package has passed the contract chain.

This option is deferred until C-12 produces a clean single-run evidence package.

## Scope

Included:

- Use a local project directory derived from the existing workflow template.
- Use a fixed known cell for the first practice.
- Run the normal Hermes preflight and approval path before any real tool execution.
- Prepare exactly one real-run package with `hermes-workflow prepare-real-run` or the equivalent library path.
- Invoke the C-7 execution adapter as execution-agent/tool-side work.
- Capture adapter logs, Spectre logs, OCEAN logs, result manifest, metric result manifest, and Hermes reports.
- Run `hermes-workflow check-real-run`.
- Run `hermes-workflow check-metric-results`.
- Run `hermes-workflow record-real-result` only after both checks pass.
- Run `hermes-workflow assess-real-run-recovery` if the adapter produces failed, partial, or metric-failed artifacts.
- Record a concise evidence summary that points to local artifact paths and hashes without committing proprietary data by default.

Excluded:

- Multi-candidate optimizer loops.
- Maestro-managed sweep or optimization.
- PSS/PAC mixer practice in the first C-12 pass.
- Formula discovery or formula repair during execution.
- Python PSF, PSFXL, raw, SST2, or waveform parsing.
- Rewriting Calculator/OCEAN formulas across dialects such as `vh`, `VT`, `drpl*`, or `harmonic`.
- Ad-hoc manual edits to returned manifests to make checks pass.
- Committing proprietary `input.scs`, PSF directories, Cadence logs, screenshots, or toolchain evidence unless the user explicitly approves a sanitized subset.
- Treating a successful terminal transcript as sufficient evidence without Hermes reports.

## Position In The Workflow

C-12 sits after C-11 and before any real optimizer loop:

```text
C-11 local/fake smoke complete
-> C-12 controlled real-tool/agent practice design
-> C-12 implementation plan
-> one approved real-run package
-> execution-agent C-7 adapter invocation
-> check-real-run
-> check-metric-results
-> record-real-result
-> decide whether to proceed to a broader real-agent loop
```

C-12 does not replace the existing C-7 adapter. It uses it in a controlled way and verifies the returned artifacts through the existing Hermes workflow tooling.

## Required Inputs

C-12 needs a local project directory with:

```text
config/project_config.yaml
config/variables.yaml
config/metrics.yaml
config/spectre.yaml
config/optimizer.yaml
netlists/exported/input.scs
```

The first practice may use a locally exported `input.scs`, but that file remains local-only unless explicitly approved for sanitized commit.

The metric formulas must already be present in `metrics.yaml` as approved OCEAN expressions before real execution. The execution agent must not infer, repair, or translate formulas while running the adapter.

The Cadence environment may be supplied through local execution configuration such as:

```text
VB_CADENCE_CSHRC=/home/zzchen/cadence_ic231_env.csh
```

This environment value is execution setup, not project truth.

## Execution-Agent Boundary

The execution agent may run only after the supervisor has an approved package.

Allowed execution command shape:

```bash
python tools/run_spectre_ocean_adapter.py PROJECT_DIR --run-id real_001
```

or an equivalent already-reviewed C-7 adapter entry point.

When invoked through the local Cadence C-shell setup, the practice plan uses `csh -fc "source ...; ..."` because the local `csh` does not support `-lc`. If the command transcript is captured with `tee`, the wrapper must preserve the adapter exit status with pipefail or must explicitly derive status from the adapter transcript and returned manifest.

The execution agent may:

- source local Cadence setup required by the adapter
- run standalone Spectre through the adapter
- run batch OCEAN through the adapter
- write result files under `runs/real/<run_id>/`
- return paths, hashes, exit codes, and logs

The execution agent must not:

- edit Hermes config files after approval
- edit `input.scs` after Hermes renders it
- edit formula text after approval
- patch manifests by hand after a failed check
- parse PSF or compute metrics outside OCEAN
- decide supervisor recovery policy

C-12 Task 3 first real invocation outcome:

- The execution-agent/C-7 adapter boundary was reached for `real_001`.
- Spectre/OCEAN were visible in the sourced Cadence shell.
- The adapter returned a structured failed `result_manifest.json` before OCEAN execution.
- The failure is evidence for the recovery path, not authorization for manual manifest repair or formula changes.

## Supervisor/Hermes Boundary

The supervisor agent may:

- run Hermes workflow CLI commands
- read machine-readable reports
- approve or reject progression
- ask the user before widening the real-tool scope

Hermes workflow tooling may:

- validate contracts
- prepare the package
- check returned manifests
- record checked results
- classify failed or partial runs

Hermes workflow tooling must not:

- run real Spectre/OCEAN during validation or recording commands
- trust execution-agent prose in place of files
- read or parse PSF data
- translate or rewrite formulas

## Evidence Layout

C-12 should write local evidence under a clearly named local directory, for example:

```text
docs/toolchain_evidence/2026-06-03-c12-controlled-real-tool-agent-practice/
```

or a scratch path selected in the implementation plan.

Evidence may include local copies or references to:

- command transcript
- environment fingerprint without secrets
- git commit hash
- project directory path
- run id
- `real_run_manifest.json`
- `result_manifest.json`
- `metric_extraction_request.json`
- `metric_result_manifest.json`
- `reports/real_run_check_report.json`
- `reports/metric_result_check_report.json`
- `reports/real_result_record_report.json`
- `reports/real_run_recovery_report.json` when applicable
- Spectre log path and hash
- OCEAN log path and hash
- scalar TSV path and hash

Default commit policy:

- Commit the design spec and implementation plan.
- Commit sanitized summary documents only when they contain no proprietary deck, PSF, model, path-sensitive, or license-sensitive content.
- Do not commit raw `input.scs`, PSF/raw directories, simulator logs, OCEAN logs, screenshots, or local toolchain evidence unless the user explicitly approves the exact files.

## Success Path

The C-12 success path is:

1. Hermes workflow tooling validates the project.
2. Hermes workflow tooling prepares netlist, dry-run, health, approval, and one real-run package.
3. The execution agent invokes the C-7 adapter for the approved run id.
4. The adapter writes `result_manifest.json` and `metric_result_manifest.json`.
5. `check-real-run` passes.
6. `check-metric-results` passes.
7. `record-real-result` passes.
8. Ledger and optimizer state contain one checked real result for the practice run.
9. The evidence summary contains enough paths, hashes, reports, and command outputs for later audit.

## Failure Path

If Spectre, OCEAN, the adapter, or a Hermes check fails, C-12 must fail closed:

1. Preserve the original returned artifacts and logs.
2. Run the appropriate Hermes check to produce a machine-readable failure report.
3. Run `assess-real-run-recovery` when a real-run package exists and is unresolved.
4. Do not manually repair returned manifests to force a pass.
5. Do not change formula text during the same practice run.
6. Do not append failure-penalty rows to the optimizer ledger.
7. Stop and report whether the failure is environment setup, Spectre execution, OCEAN formula/runtime, adapter contract, Hermes validator, or unknown.

A blocked real-tool run with preserved evidence is a valid C-12 outcome, but it is not a successful completed practice. The next scope should then be a focused diagnostic plan, not a broader optimizer loop.

## Acceptance Criteria

C-12 is accepted as a successful real-tool/agent practice only when:

- the approved package is prepared through Hermes workflow tooling
- real tool execution happens only at the execution-agent/C-7 adapter boundary
- no unapproved config, deck, or formula changes happen after approval
- returned artifacts are validated by `check-real-run` and `check-metric-results`
- `record-real-result` records the checked real result exactly once
- Python never parses PSF/waveform data or reimplements formulas
- the evidence summary is sufficient for audit
- local proprietary evidence remains uncommitted unless explicitly approved
- final spec-compliance and code-quality review gates pass

If the real adapter run fails before those conditions are met, C-12 should stop with evidence and a narrow diagnostic recommendation.

## Risks And Controls

| Risk | Control |
| --- | --- |
| Cadence license or environment instability | Treat as environment failure; record command, exit code, and logs; do not alter contracts to compensate. |
| Formula dialect mismatch | Execute only approved formula text; if OCEAN fails, stop and report formula/runtime failure. |
| Role drift between supervisor and execution agent | Label command ownership in the evidence summary and keep real tool calls out of Hermes validation commands. |
| Proprietary artifact leakage | Default to uncommitted local evidence; commit only sanitized summaries after explicit user approval. |
| Manual manifest repair | Require Hermes checks on original adapter outputs; manual edits invalidate the practice. |
| Scope creep into optimizer loop | Limit C-12 to one known cell and one real run. |

## Next Scope After C-12

If C-12 succeeds, the recommended next scope is not automatic multi-candidate optimization. The next decision should choose one of:

1. Repeat C-12 with a PSS/PAC/PNoise cell to exercise more complex OCEAN formulas.
2. Add a controlled dual-agent handoff where a real execution agent, not the supervisor, invokes the C-7 adapter.
3. Start a small real optimization loop with two or three candidates, after a new design spec defines stopping rules, evidence policy, and recovery behavior.

C-12 itself authorizes only the first controlled real-tool/agent practice gate.

## Spec Self-Review

Placeholder scan: no deferred placeholder markers or incomplete sections.

Internal consistency: C-12 keeps Hermes workflow tooling deterministic and puts physical tool execution behind the C-7 execution-agent boundary.

Scope check: the spec is intentionally limited to one known cell, one run, and one returned result check/record path.

Ambiguity check: real artifacts are local-only by default; formula text is approved before execution and never rewritten during execution.
