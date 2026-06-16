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

**Status:** Complete, verified-only.

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

**Status:** Complete, verified-only.

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

**Status:** Complete, verified-only.

Connect the runner to existing Hermes real-run contracts:

- prepare explicit optimizer-selected candidates without mutating project-level variables;
- reuse the existing real-run package writer and approval/hash/uniqueness guards for every native TuRBO candidate;
- run an injected adapter callable;
- run `check-real-run`, `check-metric-results`, and `record-real-result`;
- convert candidate-local metric failures to finite penalties and recovery decisions;
- stop on true workflow-level failures.

Tests use fake adapter callables and fake returned manifests.

No Spectre/OCEAN in automated tests.

## Task 4: CLI Wiring

**Risk:** Medium.

**Status:** Complete, verified-only.

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

**Status:** Complete, verified-only.

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

**Status:** Complete, verified-only.

Run targeted tests, ruff, cadence check, and route audit. Commit only source,
tests, and sanitized docs. Do not stage raw tool evidence.

## Completion Note

C-17 completed a clean 100-evaluation native TuRBO real-tool acceptance on
`/tmp/ic_auto_opt_c17_native_turbo_002/bridge_test_inv`.

Summary:

- `Turbo1.optimize()` drove all evaluations: 8 initialization, 92 trust-region.
- Status counts: 45 feasible, 43 constraint failed, 12 metric check failed.
- Best candidate: `real_030`, `FN=12`, `FP=2`, `WN=1.7u`, `WP=2.7u`.
- Best metrics: `rise=6.72081749122453e-11`, `fall=6.190153048273253e-11`,
  `DC=0.0003265612598325413`.
- Spectre settings stayed consistent across 100 manifests:
  `preset=ax`, `threads_per_run=10`, `parallel_jobs=10`,
  `output_format=psfxl`.
- Raw Cadence artifacts remain local-only.
