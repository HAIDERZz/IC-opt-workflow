# Fix-Run Child Parallelism Design

Date: 2026-06-17
Status: Ready for implementation
Scope: `ic-auto-opt-workflow` development package

## Problem

`fix_run` currently reuses the real Spectre/OCEAN adapter, but its orchestration
loop is serial. For a 15-corner fixed-point run, each child
`testbench x corner` simulation waits for the previous child to finish. This is
slow and underuses available Spectre licenses and CPU resources when the
requirement already contains an approved `Spectre Settings.parallel_jobs`
value.

The optimizer path already treats `parallel_jobs` as scheduler-level Spectre
process concurrency. Fix-run should use the same field for the same kind of
resource control, without adding new CLI switches or changing the adapter
contract.

## Goals

- Use `Spectre Settings.parallel_jobs` to control fix-run child concurrency.
- Keep `threads_per_run` as the per-Spectre-process `+mt` setting.
- Parallelize child `testbench x corner` runs within one fixed point.
- Keep fixed points themselves serial in the first implementation.
- Preserve all current artifact paths and report schema.
- Preserve local and remote fix-run behavior other than scheduling order.
- Keep the product CLI unchanged.
- Keep failure handling fail-closed: one child failure marks the parent
  `fix_run_report` as failed, while still collecting other child artifacts.

## Non-Goals

- No new CLI option for fix-run parallelism.
- No parallel execution across multiple fixed points in this first change.
- No changes to Spectre/OCEAN adapter internals.
- No optimizer behavior changes.
- No release package edits or GitHub publication during this development task
  unless explicitly requested after dev verification.

## User Contract

The user continues to write this requirement section:

## Spectre Settings

```yaml
engine: spectre_x
preset: ax
output_format: psfxl
threads_per_run: 10
parallel_jobs: 4
timeout_s: 7200
require_license_check: true
keep_failed_runs: true
keep_successful_runs: true
```

In `Workflow.mode: fix_run`:

- `parallel_jobs` means the maximum number of child Spectre/OCEAN runs in
  flight for one fixed point.
- `threads_per_run` means the thread count for each Spectre process.
- The rough upper CPU pressure is `parallel_jobs * threads_per_run`, subject to
  license availability and external machine limits.
- If `parallel_jobs: 1`, behavior remains serial.

The command stays unchanged:

```bash
ic-opt PROJECT_DIR --real
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

## Scheduling Model

For each fixed point:

1. Prepare the explicit candidate run with existing
   `prepare_explicit_candidate_real_run()`.
2. Discover child runs with existing `_collect_child_runs()`.
3. Run those children through a bounded `ThreadPoolExecutor`.
4. Use `max_workers = min(parallel_jobs, len(children))`.
5. Collect adapter results back on the main thread.
6. Preserve report path lists and child issues in deterministic child order.
7. Run waveform artifact gate after all child futures complete.
8. Write the same `reports/fix_run_report.json` schema.

Fixed points remain sequential:

```text
user_point_001:
  all discovered testbench/corner children run with child-level parallelism
user_point_002:
  all discovered testbench/corner children run with child-level parallelism
```

This avoids accidentally multiplying resources by
`fixed_points * parallel_jobs` in the first change.

## Local Flow

`src/hermes_workflow/fix_run_flow.py` should gain small helper functions:

- `_fix_run_parallel_jobs(project_dir: Path) -> int`
- `_run_local_child_adapter(project_root, run_id, child, cadence_cshrc) -> _ChildAdapterOutcome`
- `_run_local_child_adapters(project_root, run_id, children, cadence_cshrc, parallel_jobs) -> list[_ChildAdapterOutcome]`

The helper should call the existing `run_spectre_ocean_adapter()` exactly once
per child. It should catch exceptions and convert them to `ChildRunIssue`
instead of aborting the whole fixed point.

The main `run_fix_run_project()` loop should not append to shared lists from
worker threads. Worker threads return outcomes. The main thread converts those
outcomes into `child_issues`, `scalar_metric_manifest_paths`, and final report
entries.

## Remote Flow

`src/hermes_workflow/remote_fix_run_flow.py` should mirror the local scheduling
helper, using `run_remote_spectre_ocean_adapter()` for each child.

The existing `RemoteSshRunner` is effectively stateless around a profile and an
execute function, so it can be used by concurrent worker calls. Tests should not
assert call order on the shared mock runner. They should assert that the remote
adapter calls overlap and that the final report preserves success/failure
evidence.

Remote report sync remains after the fixed point loop completes. No partial
sync is added inside worker threads.

## Error Handling

Each child outcome has:

- `testbench_id`
- `corner_id`
- `adapter_result` when the adapter returned
- `issue` when the adapter raised or returned failure

Rules:

- Adapter exceptions become
  `ChildRunIssue(message="adapter failed: <exception message>")`.
- Non-`succeeded` adapter statuses become `ChildRunIssue`.
- Successful adapter metric manifests are collected as before.
- Waveform artifact gating remains unchanged and runs after all child outcomes
  are collected.
- Parent report status is `pass` only when there are no point issues and no
  child issues.

## Testing Strategy

No real Spectre, OCEAN, SSH, or remote host is required for unit tests.

Local tests:

- Configure `parallel_jobs: 2`.
- Create at least three fake child run directories for one fixed point.
- Patch `run_spectre_ocean_adapter()` with a side effect that tracks active
  worker count under a lock and sleeps briefly.
- Assert `max_active > 1`.
- Assert all children still appear in the report.
- Assert a failing child does not prevent other children from being collected.

Remote tests:

- Use the same active worker counter around
  `run_remote_spectre_ocean_adapter()`.
- Avoid strict call-order assertions.
- Assert failures are preserved in `child_issues`.

Regression tests:

- `parallel_jobs: 1` keeps serial behavior (`max_active == 1`).
- Scalar metrics and waveform export manifest collection remain unchanged.
- Product CLI continues to dispatch by `Workflow.mode`; no CLI flag is added.

## Documentation

Update user-facing docs after code passes:

- `README.md`
- `docs/USER_GUIDE_CN.md`
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`
- `docs/AGENT_USER_QUICKSTART_CN.md`
- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
- `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`
- `skills/ic-opt/SKILL.md`

Required wording:

- In fix-run, `parallel_jobs` controls concurrent child runs for one fixed
  point.
- In fix-run, `threads_per_run` remains per Spectre process.
- Fixed points remain serial in this version.
- Do not add a CLI override.

## Acceptance Criteria

- Local fix-run runs child testbench/corner adapters concurrently when
  `parallel_jobs > 1`.
- Remote fix-run runs child adapters concurrently when `parallel_jobs > 1`.
- `parallel_jobs: 1` preserves serial behavior.
- Existing fix-run report schema and artifact paths remain compatible.
- Unit tests cover local and remote child concurrency.
- Full test suite, ruff, and whitespace checks pass in the dev package.
- No release package edits are made unless explicitly requested after dev
  verification.
