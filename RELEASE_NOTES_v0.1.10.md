# IC Auto Opt Workflow v0.1.10

**Final release commit (release repository `ic-auto-opt-workflow-v0.1`, `main`):
`9fde562` "fix: harden real optimization workflows".** The `v0.1.10` git tag and
the GitHub Release both point at `9fde562`. Everything in this document
describes what a user gets by installing the released package or checking
out `main` at `9fde562` -- there is no separate unreleased layer.

Timeline: 2026-08-07, `0.1.9 -> 0.1.10` version bump and initial publish
(release repo `43472c0`). 2026-08-08, a same-day follow-up fix landed
(release repo `4d6929c`, netlist symlink hardening). 2026-08-08..12, a
real-world correctness audit (tracked in
`docs/audits/2026-08-10-real-world-correctness-audit-and-repair-ledger-cn.md`)
produced a larger hardening batch; per user approval this was committed as
release repo `9fde562` and **v0.1.10 was re-released at the same version
number** to point at it (tag and GitHub Release both moved from `43472c0` to
`9fde562`). There is no `0.1.10.1`/`0.1.10-post` -- the package version stays
`0.1.10` for this whole commit chain; only the git ref advanced.

Commit-hash note: this file cites the **release repository**'s hashes
(`43472c0` -> `4d6929c` -> `9fde562`). The development repository
(`ic-auto-opt-workflow`) carries the same three changes under different
hashes because its history diverges (`019a519` -> `e75e4b1`, plus the
hardening batch that became `9fde562` was developed as ~140 modified/new
files on top of dev-repo `e75e4b1`). Do not use the development-repo hashes
(`019a519`/`e75e4b1`/`b4127f8`) as release anchors; the release repository is
the anchor of record.

--------------------------------------------------------------------------

## Controller/Remote Filesystem Boundary

- Requirement checks for Remote projects resolve Remote-owned Maestro paths
  over SSH instead of probing the Controller filesystem.
- Safe file and directory symlinks inside a Maestro point root are
  materialized; broken, cyclic, special-file, and escaping links fail closed
  (release repo `4d6929c`).
- Remote candidate trees are replaced from clean staging directories, so old
  run files cannot be merged into a new candidate. This is a hardening-batch
  change (release repo `9fde562`): the `43472c0`/`4d6929c` `upload_tree()`
  was `mkdir -p` followed by `tar -xf` into the existing remote directory,
  which merges new content with whatever was already there rather than
  replacing it; the clean-staging-plus-atomic-swap behavior described here
  did not exist before `9fde562`.
- Remote report publication, artifact inventory, checksums, and retention keep
  Controller paths and Remote paths explicitly separated.

## Remote Environment and Transfer Reliability

- Staged, atomic Controller<->Remote file transfer (write/upload via a
  temporary remote path followed by `mv -f`) and Remote doctor's per-tool
  dirty-state probing.
- Workflow scripts run through explicit Remote `/bin/sh`, independent of the
  account login shell.
- SSH probe results distinguish present, absent, transport failure, and command
  failure.
- A token-owned Remote attempt lock prevents concurrent Controllers from
  mutating the same project (`src/hermes_workflow/remote_attempt_lock.py`).
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

## Upgrade Impact

An `opt_requirement.md` that passed intake/doctor under an older 0.1.x
release can start failing under this release's tightened contract. Before
rerunning an older project, check for:

- Unknown section fields or spelling mistakes anywhere in the requirement
  (previously ignored, now fail closed).
- An optimize-mode `starting_run_id` that has no effect (now rejected as
  inert instead of silently accepted).
- `History Warm Start: enabled: true` combined with a native TuRBO backend
  (`algorithm: turbo`); this combination is now rejected during
  intake/validation instead of silently ignoring the warm-start config.
- `--dry-orchestration` used outside a local first-run optimize flow; other
  combinations (continuation, fix-run, Remote) now fail before execution
  instead of being accepted and behaving unexpectedly.

## Result Credibility

- Fix-run `Metrics` is parsed and rendered instead of being silently dropped.
- Fix-run without `--real` no longer writes an empty successful report.
- Corner model/variable overrides must change the rendered deck; a misspelled
  or unmatched override fails before simulation.
- Multi-testbench corners use each testbench's own source corner.
- A new Remote attempt invalidates both optimizer and fix-run active success
  markers before preflight.

## CLI and Optimizer Capability Contract

- `--dry-orchestration` is accepted only for a local first-run optimize flow;
  unsupported combinations fail before real or Remote execution.
- `hermes-workflow continue-openbox-real` now requires and forwards
  `--additional-evals N`. This is a `hermes-workflow` developer subcommand, not
  a `ic-opt` product-CLI subcommand.
- Local and Remote `ic-opt --real --continue N` preserve the configured backend.
  Native TuRBO continuation validates cumulative history, reconstructs the
  active trust region from traces, appends only the requested evaluations, and
  preserves run/evaluation/batch numbering. This reconstruction path --
  including the `decide_continuation_real_run` supervisor-instruction rebuild
  in `src/hermes_workflow/approvals.py` -- is part of the `9fde562` hardening
  batch; a Remote native TuRBO continuation run against the earlier
  `43472c0`/`4d6929c` commits alone fails for lack of a reconstructed
  supervisor instruction (this comparison applied to the 2026-08-07 initial
  publish; it is historical background, not a caveat about the current
  release). A real Remote acceptance run verified continuation end-to-end on
  2026-08-11/12 against the released code (`9fde562`):
  `ic-opt <project> --real --continue 20 --ssh-profile <user>@<host>` extended
  a native TuRBO project from 100 to 120 cumulative evaluations (1080 child
  runs, 1200 metric manifests), with a 2400-line SHA-256 checksum inventory
  confirming the prior 100-evaluation history was preserved byte-for-byte and
  exactly 400 new checksum lines were added.
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
- `hermes-workflow check-toolchain-env` defaults to the environment containing
  the invoked `hermes-workflow`; portable task packages no longer embed a
  developer `/tmp` virtualenv path.

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
  aggregation requires an explicit `id: nominal` corner. A `fix_run` project's
  `Process Corners` section rejects an explicitly written `objective_policy`
  or `constraint_policy` during intake ("aggregation policies are not
  supported for fix_run workflow"); when both fields are omitted, intake
  fills `nominal`/`nominal` internally to satisfy schema validation only --
  fix-run has no optimizer-style aggregation to apply a policy to.
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
  dispatch. A continuation (local or Remote) re-validates the current
  requirement but does not re-materialize requirement changes into that run's
  execution config -- a warm-start section added or changed after the first
  run has no effect on a continuation.
- The packaged matrix now contains 11 parse/render-validated requirements,
  including GP-EIC, native TuRBO, multi-corner warm start, metrics-only fix-run,
  and multi-testbench Metrics+Waveform fix-run.

## Compatibility and Known Boundaries

- Native TuRBO writes and reads `reports/native_turbo_optimizer_report.json`
  and `reports/native_turbo_optimizer_evaluations.jsonl` today, not only for
  reports that predate the explicit `backend` field; the internal
  `LEGACY_NATIVE_*` constant names describe file-path origin, not current
  status. Reports without an explicit `backend` field also remain valid
  readers of the same native-specific report and JSONL paths.
- Native TuRBO trace reconstruction cannot reproduce unrecorded library RNG
  state bit-for-bit; reports state `restore_mode: trace_reconstructed`.
- `required_signals` remains provenance and history-compatibility metadata; it
  is not advertised as a pre-simulation PSF signal-existence probe.
- Slurm/LSF submission, scheduler job identifiers, and detach/reattach are
  optional future cluster integrations, not requirements or blockers for the
  current direct-SSH product scope. Remote execution in this release remains
  attached to the Controller process.

## Status

- **Software acceptance: PASS.** Wheel build and isolated-venv smoke test
  passed against this release
  (`dist/ic_auto_opt_workflow-0.1.10-py3-none-any.whl`).
- **Real Remote Native TuRBO continuation acceptance: PASS.** Verified
  2026-08-11/12 against the released code (`9fde562`):
  `ic-opt <project> --real --continue 20 --ssh-profile <user>@<host>` extended
  a native TuRBO project from 100 to 120 cumulative evaluations; see "CLI and
  Optimizer Capability Contract" above for the full evidence summary.

See
`docs/audits/2026-08-10-real-world-correctness-audit-and-repair-ledger-cn.md`
for root causes, red/green evidence, and remaining TODOs/scope decisions from
the audit that produced this release's hardening batch.

Versioning going forward: any further **code** change ships as `0.1.11` or
later -- `0.1.10` is closed at `9fde562`. A pure documentation correction (no
code change) may be committed straight to `main` without a version bump or
re-release.
