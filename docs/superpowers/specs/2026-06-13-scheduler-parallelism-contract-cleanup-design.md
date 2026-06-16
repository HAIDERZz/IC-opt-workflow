# B-02 Scheduler Parallelism Contract Cleanup Design

Date: 2026-06-13

This design fixes the B-02 requirement-contract problem: `parallel_jobs` is a real user setting, but the current file contract places it inside the Spectre runtime metadata where it is not consumed by Spectre. The goal is not to rename terminology for its own sake. The goal is to remove contradictory file-contract data and keep the user setting flowing to the part of the workflow where it actually takes effect.

## Confirmed Facts

`parallel_jobs` currently has two different meanings in different files.

As a real runtime control, it is candidate-level scheduler concurrency:

- OpenBox real evaluation builds a candidate batch evaluator with `max_workers=min(selected_parallel_jobs, selected_batch_size)`.
- Native TuRBO real evaluation builds a batch evaluator with `max_workers=min(batch_size, selected_parallel_jobs)`.
- The setting therefore controls how many candidates can be evaluated at once.

As misleading Spectre metadata, it is currently copied into:

- `runs/real/<run_id>/real_run_manifest.json` under `spectre.parallel_jobs`.
- `runs/real/<run_id>/metric_extraction_request.json` under `spectre.parallel_jobs`.
- Adapter precondition checks that require prepared/request `spectre.parallel_jobs` to match.

Spectre itself does not consume `parallel_jobs`. Single child simulation commands consume `threads_per_run` as the Spectre thread count. Multi-testbench and multi-corner child runs inside one candidate are serial:

- Remote multi-testbench/multi-corner adapter loops over `testbench_id` and `corner_id`, then synchronously calls `run_remote_spectre_ocean_adapter()`.
- Local multi-testbench/multi-corner adapter loops over `testbench_id` and `corner_id`, then synchronously calls the local Spectre/OCEAN adapter or helper script.

Therefore:

```text
simultaneous_spectre_processes <= min(optimizer.batch_size, parallel_jobs)
```

not:

```text
parallel_jobs * testbench_count * corner_count
```

## Problem

The current contract makes `parallel_jobs` look like a Spectre runtime parameter by storing and validating it inside `spectre` metadata. That is wrong for two reasons:

1. It is not passed to Spectre.
2. It is not consumed by a single child adapter run.

This creates a fake contract. The user can set `parallel_jobs`, and the setting does take effect at the scheduler level, but prepared/request files imply it is also a Spectre-level setting. Adapter validation then checks a value that the adapter does not use.

## Goals

1. Keep `parallel_jobs` as a real user-configurable setting.
2. Preserve current runtime behavior: `parallel_jobs` controls candidate-level concurrency.
3. Remove `parallel_jobs` from Spectre runtime metadata in newly generated prepared/request files.
4. Stop adapter precondition checks from requiring `spectre.parallel_jobs`.
5. Keep local and remote behavior identical.
6. Keep multi-testbench/multi-corner child runs serial inside a candidate.
7. Make reports and doctor output describe this value as scheduler/candidate parallelism, not Spectre parallelism.

## Non-Goals

- Do not change the `opt_requirement.md` user-facing field in this task.
- Do not add a new CLI flag.
- Do not add per-testbench or per-corner inner concurrency.
- Do not change `threads_per_run`.
- Do not change OpenBox or TuRBO algorithm behavior.
- Do not change remote/local adapter selection.
- Do not sync `ic-auto-opt-workflow-v0.1` until development package tests and real-flow validation pass.

## Contract Decision

For this task, keep the existing user input:

```yaml
Spectre Settings:
  parallel_jobs: 10
```

This keeps existing requirement templates and projects compatible.

Internally, interpret it as scheduler resource configuration:

```json
"scheduler": {
  "candidate_parallelism": 10
}
```

New prepared/request Spectre metadata must only contain fields that the Spectre/OCEAN child runtime consumes or directly validates as child-run runtime settings:

```json
"spectre": {
  "engine": "spectre_x",
  "preset": "ax",
  "output_format": "psfxl",
  "threads_per_run": 10,
  "timeout_s": 7200
}
```

`parallel_jobs` must not appear in this `spectre` block for newly generated files.

## Backward Compatibility

Adapters must tolerate older prepared/request files that still include `spectre.parallel_jobs`, but they must not require it. If both old files include it and the values differ, the adapter should not fail only for that difference because the field is not adapter-consumed.

Validation may still enforce:

```text
optimizer.batch_size <= spectre.parallel_jobs
```

for now because `parallel_jobs` is still stored in `config/spectre.yaml`. This is a scheduler-capacity validation, not a Spectre runtime validation. A later cleanup can move it to a dedicated resource/scheduler config section.

## Required Code Changes

Remove `parallel_jobs` from newly generated prepared/request `spectre` blocks:

- `src/hermes_workflow/real_run.py`
- `src/hermes_workflow/metric_requests.py`

Stop adapter precondition checks from requiring this field:

- `src/hermes_workflow/execution_adapters/spectre_ocean.py`

Preserve scheduler behavior:

- `src/hermes_workflow/openbox_backend.py`
- `src/hermes_workflow/native_turbo.py`
- `src/hermes_workflow/remote_optimizer_flow.py`

Update reporting wording only where it currently implies Spectre runtime meaning:

- `src/hermes_workflow/doctor_readiness.py`
- `src/hermes_workflow/remote_doctor.py`
- `src/hermes_workflow/optimizer_task_package.py`
- `skills/ic-opt/SKILL.md`
- `src/hermes_workflow/agent_skills/ic-opt/SKILL.md`

## Acceptance Criteria

1. New real-run prepared manifests do not include `spectre.parallel_jobs`.
2. New metric extraction requests do not include `spectre.parallel_jobs`.
3. Adapter precondition checks pass when prepared/request omit `spectre.parallel_jobs`.
4. Adapter precondition checks still catch real Spectre mismatches: `engine`, `preset`, `output_format`, `threads_per_run`, and `timeout_s`.
5. OpenBox and TuRBO continue using the config value as candidate-level `max_workers`.
6. Doctor/resource summary still reports candidate parallelism from the requirement/config value.
7. Multi-testbench/multi-corner child execution remains serial inside each candidate.
8. Tests prove local and remote paths share the same contract.

## Validation

Required development validation:

```bash
./.venv/bin/python -m pytest tests/test_real_run.py tests/test_metric_requests.py tests/test_spectre_ocean_adapter.py tests/test_remote_spectre_ocean.py tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_doctor_readiness.py tests/test_optimizer_task_package.py tests/test_agent_skill.py -q
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check src tests
git diff --check -- . ':!vendor' ':!.serena'
```

Required real-flow validation after implementation:

- Run a small remote multi-corner optimization using `/home/zzchen/remote_opt/Mixer_CS_muti_tb_fix_3`.
- Confirm generated prepared/request files omit `spectre.parallel_jobs`.
- Confirm scheduler/report still shows the configured candidate parallelism.
- Confirm simultaneous Spectre process count is bounded by `min(batch_size, parallel_jobs)`.
