# Native TuRBO Optimizer Runner MVP Implementation Plan

> **For agentic workers:** Keep this plan narrow. Use `superpowers:subagent-driven-development` when code risk warrants it, but do not add process artifacts beyond the files named here.

**Goal:** Productize the proven `Turbo1.optimize()` practice path into a small Hermes workflow command.

**Reference practice:** `docs/debug/2026-06-04-optimizer-skill-real-flow-practice.md`

**Active spec:** `docs/superpowers/specs/2026-06-04-native-turbo-optimizer-runner-mvp-design.md`

---

## Scope Guard

Allowed:

- add one native TuRBO runner module;
- add one CLI command;
- add focused unit/fake-runner tests;
- run one explicit real-tool acceptance after fake tests pass and the user confirms.

Forbidden:

- broad optimizer framework work;
- daemon/service/scheduler behavior;
- replacing TuRBO;
- Python PSF parsing;
- OCEAN formula rewriting;
- Maestro/ADE layout flattening;
- committing raw Cadence decks, sidecars, PSF/raw data, or full logs.

## Task 1: Core Objective And Candidate Quantization

**Risk:** Medium.

Implement a small module for:

- reading approved variables/metrics/optimizer settings from an existing project;
- mapping continuous TuRBO `x` into approved `FN/WN/FP/WP` style candidate strings;
- compact Spectre-safe unit formatting;
- feasibility-first objective calculation;
- concise evaluation trace model.

Tests:

- integer rounding;
- continuous-step snapping;
- unit suffix preservation;
- constraint violation scoring;
- feasible candidates compare by FOM;
- metric missing/non-finite returns failure penalty.

No real tools.

## Task 2: Duplicate-Aware Native TuRBO Runner

**Risk:** Medium.

Implement a runner around local `Turbo1.optimize()` that:

- calls TuRBO with `n_init = 2 * n_params`;
- supports `max_evals`;
- de-duplicates after quantization;
- tries bounded replacement candidates before consuming a real evaluation;
- records initialization vs trust-region phases.

Tests:

- duplicate quantized candidates trigger replacement;
- no replacement left returns finite duplicate penalty and records status;
- `Turbo1.optimize()` is the driver, not the C-13 one-candidate suggestion loop.

No real tools.

## Task 3: Hermes Real Evaluator Adapter

**Risk:** High.

Connect the runner to existing Hermes real-run contracts:

- prepare the first explicit optimizer candidate without mutating project-level variables;
- prepare later candidates through `prepare_candidate_real_run`;
- run an injected adapter callable;
- run `check-real-run`, `check-metric-results`, and `record-real-result`;
- convert candidate-local metric failures to finite penalties and recovery decisions;
- stop on true workflow-level failures.

Tests use fake adapter callables and fake returned manifests.

No Spectre/OCEAN in automated tests.

## Task 4: CLI Wiring

**Risk:** Medium.

Add:

```bash
hermes-workflow run-native-turbo PROJECT_DIR \
  --max-evals N \
  --cadence-cshrc PATH
```

The command should:

- use approved Spectre settings;
- run sequentially in MVP;
- write `reports/native_turbo_optimizer_report.json`;
- write `reports/native_turbo_optimizer_evaluations.jsonl`;
- exit non-zero for workflow-level failure.

Tests use fake runners only.

## Task 5: Real Tool Acceptance

**Risk:** High; user-confirmed only.

Run one real practice on `bridge_test_inv` from a clean `/tmp` project:

- `max_evals=100`;
- exact approved formulas;
- native Maestro/ADE netlist layout;
- `+preset=ax`;
- `+mt=10`;
- simultaneous Spectre process count <= `parallel_jobs`.

Acceptance:

- the command completes;
- at least one trust-region candidate is evaluated after initialization;
- trace contains every candidate and status;
- best candidate is reported;
- duplicate and metric-failure counts are visible;
- raw Cadence artifacts stay local-only.

## Task 6: Closeout

Run targeted tests, ruff, cadence check, and route audit. Commit only source,
tests, and sanitized docs. Do not stage raw tool evidence.
