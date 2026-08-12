# IC Auto Opt Workflow v0.1.10

Maintenance baseline: 2026-08-12

v0.1.10 keeps the existing package version while hardening the real local and
Remote workflows. The maintenance work is intentionally compatibility-focused:
it does not change optimizer algorithms or the package version, but it now
rejects requirement fields that previously looked valid while having no real
effect.

## Controller/Remote Filesystem Boundary

- Requirement checks for Remote projects resolve Remote-owned Maestro paths
  over SSH instead of probing the Controller filesystem.
- Remote candidate trees are replaced from clean staging directories, so old
  run files cannot be merged into a new candidate.
- Safe file and directory symlinks inside a Maestro point root are materialized;
  broken, cyclic, special-file, and escaping links fail closed.
- Remote report publication, artifact inventory, checksums, and retention keep
  Controller paths and Remote paths explicitly separated.

## Result Credibility

- Fix-run `Metrics` is parsed and rendered instead of being silently dropped.
- Fix-run without `--real` no longer writes an empty successful report.
- Corner model/variable overrides must change the rendered deck; a misspelled
  or unmatched override fails before simulation.
- Multi-testbench corners use each testbench's own source corner.
- A new Remote attempt invalidates both optimizer and fix-run active success
  markers before preflight.

## Remote Environment and Transfer Reliability

- Workflow scripts run through explicit Remote `/bin/sh`, independent of the
  account login shell.
- SSH probe results distinguish present, absent, transport failure, and command
  failure.
- A token-owned Remote attempt lock prevents concurrent Controllers from
  mutating the same project.
- Tree/file transfer uses deadlines, staging, and atomic publication.
- Remote doctor checks Controller transfer tools, Remote POSIX/GNU tools, and
  Spectre/OCEAN independently.
- Remote preparation snapshots are retained with bounded garbage collection.
- Dirty-state directory enumeration now treats every nonzero command result as
  an error and preserves Remote stderr; transport or command failures cannot be
  reported as an empty run directory.
- Every Remote continuation attempt reruns Doctor once against the current
  Remote environment before frozen preparation, history synchronization, or
  backend dispatch.
- Fix-run and multi-testbench aggregate manifests use the actual current UTC
  execution time instead of hard-coded 2026 provenance values.

## CLI and Optimizer Capability Contract

- `--dry-orchestration` is accepted only for a local first-run optimize flow;
  unsupported combinations fail before real or Remote execution.
- `continue-openbox-real` now requires and forwards
  `--additional-evals N`.
- Local and Remote `ic-opt --real --continue N` preserve the configured backend.
  Native TuRBO continuation validates cumulative history, reconstructs the
  active trust region from traces, appends only the requested evaluations, and
  preserves run/evaluation/batch numbering.
- Legacy sequential Native histories are normalized as single-point batches;
  partial or incoherent batch metadata fails closed. Related Native reports are
  published transactionally so a failed continuation cannot leave mixed
  generations.
- Continuation closeout and packaged audit commands require the configured
  backend, so stale OpenBox artifacts cannot mask a current Native result.
- Fresh optimize closeout applies the same backend requirement. Standalone task
  packaging resolves implicit OpenBox, Native, and random-baseline projects from
  project configuration and rejects a conflicting explicit backend.
- Optimizer task packages support both OpenBox and Native continuation and
  reject fix-run or warm-start/continuation combinations before writing files.
- Enabled History Warm Start is explicitly OpenBox-only; native TuRBO projects
  are rejected during intake/validation instead of silently ignoring history.
- `check-toolchain-env` defaults to the environment containing the invoked
  `hermes-workflow`; portable task packages no longer embed a developer `/tmp`
  virtualenv path.

## Requirement and Scientific-Semantics Contract

- `Workflow` is parsed by the same strict model used at execution time. Unknown
  modes, optimize-only/fix-run-only section mismatches, and inert optimize
  `starting_run_id` values fail during intake/doctor.
- Unknown section fields and spelling mistakes fail closed. Regenerating a
  project from a changed requirement removes stale managed config files instead
  of letting an earlier mode or section remain active.
- Metric and waveform routes are explicit for multi-testbench projects and
  omitted for single-testbench projects. Every declared testbench must own at
  least one scalar or waveform extraction. Waveform names are unique,
  expressions are non-empty, and the only supported nil policy is `fail`.
- Constraint thresholds must be finite numbers followed by the exact unit of
  their Metric. Objective parsing and runtime evaluation share one whitelist:
  arithmetic (including modulo), `min`, `max`, and `ln`. Runtime domain or
  arithmetic errors fail only the affected candidate with the configured
  penalty instead of aborting the optimizer.
- Fixed points are checked before simulation for complete parameter coverage,
  bounds, step grid, unit suffix, unique candidate IDs, and `real_NNN` range.
- Corner variable/model overrides must match the rendered deck. `model_file`
  is a safe absolute path, must identify exactly one include, and must be a
  readable regular file on the machine that runs Spectre (Remote host for
  Remote flows). Each testbench uses its own source corner, and nominal
  aggregation requires an explicit `id: nominal` corner.
- Fixed OpenBox presets cannot be silently changed by contradictory advanced
  settings. Optimizer batch/parallel limits and the TuRBO minimum budget are
  enforced during requirement intake as well as project validation.
- Fix-run retention settings now apply once per fixed point. In Remote mode the
  Remote run and Controller snapshot decisions are synchronized before the
  authoritative completion report.
- Remote optimizer retention now uses the final post-record observation for
  both OpenBox and native TuRBO, including continuation; a record failure can
  no longer be classified remotely as a successful run.
- History warm-start config is included in execution-package immutable hashes,
  and public optimizer entry points reject fix-run projects before optimizer
  execution. Local entry points fail before doctor/preparation; Remote
  continuation validates its frozen snapshot first, then fails before backend
  dispatch.
- The packaged matrix now contains 11 parse/render-validated requirements,
  including GP-EIC, native TuRBO, multi-corner warm start, metrics-only fix-run,
  and multi-testbench Metrics+Waveform fix-run.

## Compatibility and Known Boundaries

- Existing native TuRBO reports that predate the explicit `backend` field remain
  valid when they use the native-specific report and JSONL paths.
- Native TuRBO trace reconstruction cannot reproduce unrecorded library RNG
  state bit-for-bit; reports state `restore_mode: trace_reconstructed`.
- `required_signals` remains provenance and history-compatibility metadata; it
  is not advertised as a pre-simulation PSF signal-existence probe.
- Slurm/LSF submission, scheduler job identifiers, and detach/reattach are
  optional future cluster integrations, not requirements or blockers for the
  current direct-SSH product scope. Remote execution in this release remains
  attached to the Controller process.

## Final Acceptance

- The release checkout passed its software acceptance with `1757 passed`,
  Ruff clean, `git diff --check` clean, version `0.1.10`, all 11 requirement
  templates validated, and wheel metadata/content plus isolated CLI smoke
  checks passing.
- The isolated real Remote Native TuRBO project continued from the existing
  100 evaluations by exactly 20 without rerunning initialization. The final
  result contains 120 parent runs, 1080 child runs, 1200 metric manifests, and
  2400 checksum entries; all 2400 Remote checksums passed.
- The first 100 history rows and their 2000 artifact checksums remained
  unchanged. The final flow passed with Native backend, Remote transport,
  reconstructed trust-region state, accepted artifacts, successful
  finalization, and no active attempt lock.
- Real continuation exposed one release-blocking defect: a frozen Controller
  cache did not contain `supervisor_instruction.json`. Continuation now
  regenerates a fail-closed instruction from the execution manifest and
  current validated config before the real optimizer gate. Its focused tests
  pass (`87 passed`); this small correction did not trigger another full suite.

## Deferred Work

- Slurm/LSF job IDs, scheduler submission, and detach/reattach remain future
  production capabilities, not incomplete behavior in the direct-SSH flow.
- Log wording, additional diagnostics, reject-reason propagation, optimizer
  state naming clarification, extreme-concurrency hardening, and broader fault
  matrices are deferred. They do not change the accepted v0.1.10 results.
- Local continuation does not reconstruct an externally deleted approval file;
  it remains fail-closed and is deferred separately from the validated Remote
  continuation path.

See
`docs/audits/2026-08-10-real-world-correctness-audit-and-repair-ledger-cn.md`
for root causes, red/green evidence, real Remote acceptance evidence, remaining
TODOs, and scope decisions.
