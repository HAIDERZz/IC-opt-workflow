# Optimizer Run Acceptance Audit Design

Date: 2026-06-04

## Goal

Add the smallest deterministic supervisor/Hermes audit command for a completed
native TuRBO optimizer run.

C-24 proved that the generated optimizer execution-agent packet can drive
`run-native-turbo --parallel --max-evals 100`, but acceptance still required a
manual manifest-level audit. C-25 turns that audit into a reusable Hermes check.

## Non-Goals

- Do not run Virtuoso, Spectre, OCEAN, SSH, or execution agents.
- Do not add an optimizer algorithm, scheduler, daemon, service, or database.
- Do not rerun failed candidates.
- Do not parse PSF or waveform data in Python.
- Do not rewrite OCEAN formulas.
- Do not change approved metrics or constraints.
- Do not flatten or redesign the Maestro/ADE netlist layout.
- Do not commit raw Cadence decks, protected sidecars, PSF/raw data, or full
  Cadence logs.

## User-Level Behavior

Expose one narrow command:

```bash
hermes-workflow check-optimizer-run PROJECT_DIR
```

The command reads existing optimizer artifacts from `PROJECT_DIR`:

```text
reports/native_turbo_optimizer_report.json
reports/native_turbo_optimizer_evaluations.jsonl
state/optimizer_state.json
ledger/experiment_ledger.jsonl
runs/real/*/result_manifest.json
runs/real/*/metrics/metric_result_manifest.json
```

It writes:

```text
reports/optimizer_run_acceptance_report.json
```

The command does not decide from process exit status alone. It accepts or
rejects from report, trace, result manifest, metric manifest, and settings
consistency.

## Acceptance Semantics

A completed optimizer run is accepted when:

- native TuRBO report exists and has `status = completed`;
- JSONL trace row count equals `evaluation_count`;
- each trace row has a `run_id` and `result_manifest`;
- result manifests exist for all trace rows with real runs;
- result manifests are not accepted from command exit status alone;
- metric manifests exist when the result manifest references them;
- metric manifest failures are allowed only as candidate-level failures that
  are reflected in the optimizer trace status;
- Spectre settings are consistent with configured expectations:
  - `preset`
  - `threads_per_run`
  - `parallel_jobs`
  - `output_format`
- required returned artifacts from the optimizer task packet exist when the
  packet manifest is present.

The audit should reject clear workflow drift:

- missing native TuRBO report;
- unreadable JSON or malformed JSONL;
- evaluation count mismatch;
- missing result manifest for a traced run;
- missing metric manifest for a successful result;
- result manifest status failure recorded as feasible;
- metric command failure not reflected as `metric_check_failed` or a classified
  candidate-level failure;
- Spectre setting drift;
- report says completed but all physical result manifests failed.

## State/Ledger Handling

`state/optimizer_state.json` is currently a running optimizer snapshot in the
native runner. C-18, C-21, and C-24 accepted runs show `status = running` while
the final run report is `completed`.

C-25 must not make `state.status = completed` a blocker. The canonical
completion source is:

```text
reports/native_turbo_optimizer_report.json
```

The audit may include state and ledger counts as warnings or summary fields, but
must not reject solely because state is a running snapshot.

## Output Report

`optimizer_run_acceptance_report.json` should contain:

```json
{
  "schema_version": "1.0",
  "status": "accepted",
  "evaluation_count": 100,
  "result_manifest_count": 100,
  "metric_manifest_count": 100,
  "status_counts": {
    "feasible": 36,
    "constraint_failed": 43,
    "metric_check_failed": 21
  },
  "settings": {
    "preset": "ax",
    "threads_per_run": 10,
    "parallel_jobs": 10,
    "output_format": "psfxl"
  },
  "best_candidate": {
    "run_id": "real_021",
    "parameters": {
      "FN": "10",
      "WN": "1.1u",
      "FP": "9",
      "WP": "0.5u"
    },
    "objective": 4.305718220077049e-14
  },
  "issues": [],
  "warnings": []
}
```

Use `status = rejected` when any blocking issue exists.

## Evidence Basis

C-25 is based on the successful C-24 Task 2R evidence:

```text
docs/debug/2026-06-04-c24-generated-task-packet-handoff.md
```

C-25 should encode that audit behavior. It should not invent a different
acceptance model.

## Route Alignment

This design directly supports the original project purpose: keep the supervisor
agent from manually interpreting a large pile of real-tool files and give it one
deterministic report for accepting or rejecting execution-agent optimizer work.

It preserves the current execution split:

```text
Execution agent runs generated packet in non-sandbox Cadence environment
-> Hermes workflow tooling audits returned artifacts deterministically
-> Supervisor agent reads one acceptance report and decides the next step
```
