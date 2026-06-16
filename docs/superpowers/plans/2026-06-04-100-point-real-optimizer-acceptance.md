# C-16 100-Point Real Optimizer Acceptance Plan

> **For agentic workers:** Keep this plan lean. Do not create a broad optimizer framework. The goal is to run the real optimizer loop and fix only real blockers exposed by that run.

**Goal:** Prove the current Hermes + TuRBO + Spectre/OCEAN loop can run a meaningful fixed-budget optimization, not just a few hand-picked points.

**Architecture:** C-16 uses the existing C-15 loop driver and C-7 Spectre/OCEAN adapter. The execution agent is not part of the normal candidate loop; it remains optional for Virtuoso/Maestro setup/export/debug.

**Baseline project:** `/tmp/ic_auto_opt_c14/bridge_test_inv`

## Scope Guard

Allowed:

- Continue the existing real optimizer project from 3 recorded rows toward `max_evaluations = 100`.
- Use the existing C-15 loop driver and C-7 adapter.
- Fix blockers directly exposed by the real 100-point run.
- Record concise local-only evidence under `/tmp`.

Forbidden:

- Do not add a broad optimizer framework, daemon, scheduler, queue, service, or parallel batch runner.
- Do not parse PSF in Python.
- Do not rewrite OCEAN formulas.
- Do not replace the native Maestro/ADE netlist layout.
- Do not commit raw Cadence artifacts, protected sidecars, PSF/raw data, full logs, `docs/OCEAN_DOC_*`, or `docs/toolchain_evidence/`.

## Task 0: Spectre Run Settings Contract Alignment

**Status:** complete, verified-only.

**Reason:** C-16 is invalid unless every point uses the requested Spectre precision and parallel settings.

Requirements:

- `metric_extraction_request.json` carries `spectre.parallel_jobs`.
- C-7 adapter rejects request/prepared Spectre setting drift.
- C-7 Spectre argv uses requested `preset`, `threads_per_run`, and `output_format`.
- `spectre.threads_per_run` is rendered as Spectre `+mt=<threads_per_run>` and means per-Spectre-process thread count.
- For existing approved smoke workspaces created before this field, omitted `threads_per_run` is interpreted as `10` to avoid invalidating approved config hashes during C-16 continuation.
- `spectre.parallel_jobs` is treated as the maximum number of simultaneously launched Spectre processes, not as the Spectre `+mt` thread count.
- C-16 uses a sequential loop, so actual concurrent Spectre process count is `1`, which must stay within `parallel_jobs`.
- `result_manifest.json` records actual `preset`, `threads_per_run`, `output_format`, and `timeout_s`.
- `check-real-run` fails if recorded simulator settings drift from the prepared manifest.

Verification:

```bash
python3 -m pytest tests/test_spectre_ocean_adapter.py tests/test_result_handoff.py tests/test_metric_results.py -q
python3 -m pytest tests/test_candidate_injection_real_run.py tests/test_real_run.py tests/test_next_real_run.py tests/test_real_result_record.py -q
python3 -m ruff check src tests tools
```

Task 0 result:

- `metric_extraction_request.json` now carries `spectre.parallel_jobs`.
- C-7 adapter rejects request/prepared Spectre setting drift.
- C-7 Spectre argv uses requested `preset`, `threads_per_run`, and `output_format`.
- Generated result manifests record simulator `preset`, `threads_per_run`, `output_format`, and `timeout_s`.
- `threads_per_run` is mapped to Spectre `+mt`; current project value is `10`.
- `check-real-run` fails if recorded simulator settings drift from the prepared manifest.
- `parallel_jobs` is not mapped to Spectre `+mt`.
- Final verification passed: `python3 -m pytest -q` (492 passed), `python3 -m ruff check src tests tools`, `python3 tools/check_development_cadence.py`, and `git diff --check`.

## Task 1: 100-Point Sequential Real Optimizer Run

**Status:** complete with blockers found.

Run only after Task 0 is committed.

Expected start state:

- `/tmp/ic_auto_opt_c14/bridge_test_inv/state/optimizer_state.json` has `current_evaluations = 3`.
- `config/optimizer.yaml` has `max_evaluations = 100`.
- `config/spectre.yaml` has `preset = ax`, `output_format = psfxl`, and `parallel_jobs = 10`; `threads_per_run` is explicitly `10` in new templates and defaults to `10` for the existing C-16 smoke workspace.

Run command shape:

```bash
csh -fc "source /home/zzchen/cadence_ic231_env.csh; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; setenv PYTHONPATH src:../TuRBO; .venv/bin/python tools/run_real_optimizer_loop.py /tmp/ic_auto_opt_c14/bridge_test_inv --max-new-evaluations 97 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh"
```

Acceptance:

- The run reaches 100 recorded evaluations, or stops with a clearly classified real blocker.
- After the first 8 finite observations, new candidate requests must include `selection_mode = turbo` unless the run stops before that point.
- Every new result manifest records `preset = ax`, `threads_per_run = 10`, and `output_format = psfxl`.
- Every new run request/prepared manifest keeps `threads_per_run = 10` as per-Spectre-process `+mt` and `parallel_jobs = 10` as the maximum concurrent Spectre process cap.
- The C-16 run remains sequential unless a later plan explicitly introduces a parallel runner; actual concurrent Spectre process count is therefore `1 <= parallel_jobs`.
- No run uses a different precision setting.
- Tool/environment failures stop the run for debugging.
- Candidate-level metric failures become the next real blocker to productize as penalty observations; do not disguise them as OCEAN/formula bugs.

Task 1 result:

- The project reached `current_evaluations = 100` and `optimizer_state.status = completed`.
- The first 55 recorded rows were produced before the TuRBO environment was fixed. Their candidate requests used `selection_mode = initialization_fallback`.
- Root cause: system `python3` had Hermes dependencies but lacked `torch/gpytorch`; project `.venv` had `torch/gpytorch` but lacked Hermes dependencies. Installing the project into `.venv` fixed the environment split.
- `real_056` had completed result/metric manifests when the invalid fallback run was stopped; it was checked with Hermes contracts and recorded successfully.
- The resumed run used `.venv` and produced `real_057` through `real_100`.
- `real_057` through `real_091`, `real_093`, and `real_095` through `real_100` used `selection_mode = turbo`.
- `real_092` and `real_094` still used `selection_mode = initialization_fallback` after the TuRBO environment was fixed. This means TuRBO candidate generation can still silently fall back, likely after quantization/deduplication.
- Spectre/OCEAN contracts passed for all new runs: `check-real-run` and `check-metric-results` passed for `real_004` through `real_100`.
- Spectre settings were consistent for `real_004` through `real_100`: `preset = ax`, `threads_per_run = 10`, `output_format = psfxl`, and `parallel_jobs = 10`.
- Ledger summary: `100` rows total, `8` `real_pass`, `92` `real_constraint_fail`, no recorded tool failures, no recorded metric failures.

## Task 2: Closeout

**Status:** complete with follow-up required.

Summarize:

- total evaluations attempted;
- total recorded;
- pass/constraint-fail/tool-fail/metric-fail counts;
- best candidate id, run id, objective, and metrics;
- whether TuRBO actually took over after initialization;
- any blocker that must be fixed before broader use.

Closeout:

- Total recorded: `100`.
- Pass/constraint/tool/metric counts: `8 real_pass`, `92 real_constraint_fail`, `0 tool failures`, `0 metric failures`.
- Best feasible candidate remains `candidate_000003` / `real_003`, objective `4.4591643476084205e-14`, parameters `FN=6`, `FP=4`, `WN=2.4u`, `WP=1.4u`, metrics `DC=0.0003515194271758733`, `fall=6.17648525412794e-11`, `rise=6.508914194299693e-11`.
- TuRBO did take over after the environment fix: `real_057` onward mostly used `selection_mode = turbo`.
- C-16 is not a clean optimizer acceptance because `real_092` and `real_094` silently fell back to initialization after TuRBO was available.
- Next required work: a narrow TuRBO suggestion robustness fix. Do not run another broad 100-point acceptance until fallback is surfaced, retried, or classified instead of silently using initialization.
