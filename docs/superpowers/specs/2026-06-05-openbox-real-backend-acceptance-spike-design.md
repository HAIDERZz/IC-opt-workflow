# OpenBox Real Backend Acceptance Spike Design

Date: 2026-06-05

## Purpose

C-28 validates whether OpenBox should become a real optimizer backend candidate for this workflow. It is an evidence-gathering spike, not a production replacement for the native TuRBO route.

The question is narrow:

```text
Can OpenBox generate real batch candidates for the existing Spectre/OCEAN execution path,
write the backend-neutral optimizer artifacts added in C-27,
and pass the existing C-25/C-26 supervisor audit?
```

## Background

The project already has a working real optimization route:

```text
native TuRBO batch candidate generation
-> existing real candidate package / Spectre / OCEAN adapter
-> real result and metric manifests
-> native_turbo_optimizer_report.json / native_turbo_optimizer_evaluations.jsonl
-> check-optimizer-run
-> summarize-optimizer-run
```

C-27 added a backend-neutral artifact seam:

```text
reports/optimizer_run_report.json
reports/optimizer_evaluations.jsonl
```

and proved a fake OpenBox backend can write artifacts that C-25 and C-26 can read. C-28 tests the missing real-tool part.

## Scope

C-28 will run one scoped real-tool OpenBox acceptance spike using a known-good inverter project and the already proven Spectre/OCEAN execution path.

The spike must:

- Use OpenBox ask-and-tell or batch suggestion APIs.
- Use the approved project `variables.yaml`, `metrics.yaml`, `optimizer.yaml`, and `spectre.yaml`.
- Preserve native Maestro/ADE/Spectre project structure.
- Use the existing candidate preparation, Spectre/OCEAN adapter, metric checks, and result recording path.
- Write backend-neutral optimizer artifacts.
- Run `check-optimizer-run` and `summarize-optimizer-run`.
- Compare the OpenBox run shape against the accepted native TuRBO baseline.

## Non-Goals

C-28 must not:

- Replace or delete `src/hermes_workflow/native_turbo.py`.
- Add a broad optimizer framework.
- Add a daemon, service, database, or distributed scheduler.
- Change approved metric formulas.
- Translate OCEAN expressions into Python.
- Parse PSF or waveform files in Python.
- Flatten or redesign native Maestro/ADE netlist layout.
- Claim a global optimum from a partial run.
- Commit raw `input.scs`, protected include decks, PSF/raw data, full Cadence logs, or local environment files.

## Backend Decision Rules

C-28 can only recommend OpenBox productization if all of these are true:

- OpenBox can generate stepped/discrete candidate values without off-grid drift after Hermes quantization.
- It can run at least one 100-evaluation batch-mode real-tool acceptance with the same Spectre settings discipline as TuRBO.
- It produces backend-neutral artifacts accepted by C-25.
- C-26 can summarize the run and produce a continuation/completion decision.
- Failures are classifiable as candidate-level constraint/metric failures or true real-tool failures.

C-28 must recommend staying with TuRBO for now if:

- OpenBox setup is unstable in the local environment.
- OpenBox suggestions repeatedly collide after quantization.
- OpenBox cannot support the current batch ask-and-tell loop without invasive framework work.
- Real-tool audit fails for reasons not present in the native TuRBO route.

## Spectre Settings Contract

C-28 must keep the same precision and resource semantics used by the accepted TuRBO path:

- Spectre preset comes from `config/spectre.yaml`, currently `ax`.
- `threads_per_run` maps to Spectre `+mt`, currently `10`.
- `parallel_jobs` means concurrent Spectre processes, not Spectre `+mt`.
- The spike must audit all successful result manifests for consistent `preset`, `threads_per_run`, `parallel_jobs`, and `output_format`.

## Result Semantics

C-28 reports the best candidate as `best_observed`, not global optimum, unless the full finite design space has been exhausted.

The report must separate:

- `feasible`: all constraints passed.
- `constraint_failed`: valid metrics, but specs not met.
- `metric_check_failed`: OCEAN returned non-scalar, nil, or non-finite metric result for a candidate.
- `real_check_failed`: Spectre/OCEAN tool execution artifact failed.
- setup/environment blockers.

## Evidence Artifacts

Committed evidence may include only sanitized summaries:

- `docs/debug/2026-06-05-openbox-real-backend-acceptance-spike.md`
- Updated progress/checkpoint files.

Raw artifacts stay local-only under `/tmp`.

## Acceptance Criteria

C-28 is accepted if it produces one of these explicit decisions:

```text
proceed_to_openbox_productization
keep_openbox_fake_only_for_now
reject_openbox_real_backend_for_now
```

The decision must cite:

- OpenBox candidate count and batch count.
- Feasible / constraint_failed / metric_check_failed / real_check_failed counts.
- Best observed candidate.
- Spectre settings audit.
- Duplicate or off-grid quantization issues.
- C-25 acceptance result.
- C-26 completion decision.

## Route Audit

This design remains aligned with the top-level project plan because it preserves Hermes as lightweight workflow tooling and keeps the execution side grounded in the proven Spectre/OCEAN path. The only new question is optimizer candidate generation backend viability.
