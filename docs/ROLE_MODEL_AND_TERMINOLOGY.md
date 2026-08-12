# Role Model And Terminology

This release uses a file-based product workflow:

```text
User -> opt_requirement.md -> ic-opt CLI -> Spectre/OCEAN/optimizer -> artifacts -> user or agent review
```

For a remote run (`--ssh-profile PROFILE`), the CLI additionally runs as a
Controller driving a separate Remote host over SSH — see "Controller /
Remote / Controller Cache" below.

## Workflow Mode（工作流模式）

`opt_requirement.md`'s `## Workflow` section sets `mode`, one of:

- **`optimize`**（优化）: the algorithm/strategy selected in
  `opt_requirement.md` (see
  [OPTIMIZER_ALGORITHM_MODES.md](OPTIMIZER_ALGORITHM_MODES.md)) proposes
  candidate parameter points and learns from each observation.
- **`fix_run`**（定点跑批）: runs a fixed, user-listed set of parameter
  points once each. It does not use an optimizer strategy, does not create
  optimizer state, and does not produce an optimizer decision report; it
  records Spectre/OCEAN artifacts and, when requested, waveform exports for
  each fixed point.

Most terms below apply to both modes; where a term is optimize-only or
fix_run-only, that is called out explicitly.

## User

The user owns circuit intent and approves machine-critical inputs in
`opt_requirement.md`: workflow mode, variables, metrics, constraints,
objective, fixed points, waveform exports, simulator resources, optimizer
settings, and process corners.

## Agent

The recommended agent instruction is `skills/ic-opt/SKILL.md` (a path
relative to the release root; it is not installed into the Python
environment created by `requirements-product.txt`, so confirm it shipped
alongside the release you are using).

The agent may:

- read `opt_requirement.md`
- run `ic-opt PROJECT_DIR --doctor`
- run `ic-opt PROJECT_DIR --real`
- run `ic-opt PROJECT_DIR --real --dry-orchestration` (local first-run
  `optimize` workflow only; not for `fix_run`, not combinable with
  `--ssh-profile` or `--continue`)
- run `ic-opt PROJECT_DIR --real --continue N`
- run the same four commands prefixed with `--ssh-profile PROFILE` to drive
  a Remote host as Controller — see
  [TOOLCHAIN_EXECUTION_REFERENCE.md](TOOLCHAIN_EXECUTION_REFERENCE.md) for
  the full command list and remote-mode constraints
- inspect reports and manifests
- explain the selected candidate and warnings
- explain fix-run waveform CSV evidence and child failures

The agent must not:

- invent candidate points
- rewrite OCEAN formulas
- parse PSF in Python
- change search space, resources, strategy, initialization, or process corners
  outside `opt_requirement.md`
- treat chat text as proof when artifacts show failure

In practice, the "must not" list above is the human-readable summary of the
`forbidden_actions` recorded in the **Supervisor Instruction** (below) for an
approved run: `modify_maestro_setup`, `modify_immutable_config_files`,
`change_variable_bounds`, and `change_objective_or_constraints`. When a run
is rejected, `forbidden_actions` collapses to
`run_standalone_spectre_optimizer` — i.e. the agent must not attempt the real
run at all until the rejection reason is resolved.

## Product CLI

`ic-opt` is the product entrypoint. It reads project files, runs validation,
launches real workflow steps, and writes reports.

## Controller / Remote / Controller Cache（远程角色模型）

`CONTEXT.md` at the release root is the canonical remote-mode terminology
glossary (Controller, Remote Host, Controller Cache, Remote-owned Path,
Materialized Artifact, Remote Preparation Snapshot, Remote Attempt Lock,
Continuation, Remote History Manifest, Remote Acceptance Run) and explicitly
defers the User/Agent/CLI role model to this file. The entries below stay
consistent with `CONTEXT.md`'s definitions and add the report/CLI detail this
file's other sections already carry; where the two overlap, `CONTEXT.md` is
authoritative for the term's wording.

Remote mode (`--ssh-profile PROFILE`) splits execution across two hosts:

- **Controller**（控制端）: the machine invoking `ic-opt --ssh-profile ...`.
  It never runs Spectre/OCEAN itself in remote mode; it drives the Remote
  host over SSH and only ever touches Remote-owned files through that
  transport or through the Controller Cache below.
- **Remote**（远程端 / 执行端）: the Linux EDA server that actually owns
  `REMOTE_PROJECT_DIR` and runs Virtuoso/Spectre/OCEAN. This is also where
  the Cadence cshrc, the project's real evidence (`reports/`, `runs/`,
  `ledger/`, `state/`), and the **Remote Attempt Lock** (below) live.
- **Controller Cache**（控制端缓存）: a local, per-(profile, remote
  directory) working copy on the Controller, at
  `~/.ic-opt/remote_runs/<ssh_profile>/<sha256(profile + remote_dir)[:16]>`.
  It is materialized fresh on every `prepare` step (any pre-existing cache
  directory for that key is deleted and rebuilt), so it is not a persistent
  workspace — do not expect its contents to survive across independent
  `--real` invocations except through the mechanism described under
  **Remote Preparation Snapshot** below. `config/*.yaml` is
  materialized only into the Controller Cache; it is one of the things that
  never gets published back to the Remote host. See
  [docs/adr/0001-remote-filesystem-boundary.md](adr/0001-remote-filesystem-boundary.md)
  for the isolation rule and its rationale (fail closed, no same-named-path
  fallback).

## Supervisor Instruction（监督者指令）

Before a real run is allowed to touch Spectre, the flow writes
`supervisor_instruction.json` at the project root (Controller Cache root in
remote mode). It records one of three decisions:

- `approve_first_real_run` — the requirement, execution manifest, and
  (for a first run) preflight reports are all in order; `allowed_actions`
  names what the run may do (e.g. `run_standalone_spectre_optimizer` for
  optimize, `prepare_fixed_candidate_real_run` for fix_run).
- `reject_first_real_run` — validation, the execution manifest, or
  preflight readiness failed; `forbidden_actions` is
  `run_standalone_spectre_optimizer`, and `allowed_actions` is limited to
  writing an escalation report and revising the execution package.

There are three decision entry points, matching the three real-run shapes:
a first optimize real run, a continuation real run, and a fix-run real run.
**Continuation is special**: a remote continuation rebuilds its Controller
Cache from the **Remote Preparation Snapshot** (see below), which never
contains a supervisor instruction or preflight reports from the prior run.
Continuation's approval therefore only revalidates the immutable config
against the execution manifest — preflight readiness for that decision is
replaced by **prior history acceptance**（既有 history 验收门槛）: before a
continuation is allowed to append evaluations, the flow re-runs the same
acceptance check used to produce `reports/optimizer_run_acceptance_report.json`
(`check_optimizer_run(..., expected_backend=backend)`) against the history
recorded by the *prior* run. If that prior history is not `accepted`, the
continuation is refused with `prior optimizer history acceptance rejected:
<issues>` before any new Spectre evaluation runs.

Every decision, approved or rejected, also carries `approved_config_hashes`
(the immutable config file hashes from the execution manifest) so a later
step can detect that the config changed after approval.

## Continuation（续跑，Trace-Reconstructed State）

`ic-opt PROJECT_DIR --real --continue N` (or the same with `--ssh-profile`)
extends an existing optimize run by `N` additional evaluations. Continuation
re-validates the current requirement (local: `check_requirement()` in
`product_cli.py`; remote: Doctor re-parses the remote `opt_requirement.md` in
`remote_doctor.py`), but it does not re-materialize requirement changes into
this run's execution config: it resolves algorithm, strategy, batch size, and
every other optimizer setting from `config/optimizer.yaml` (materialized on
the first run) — the CLI only supplies the evaluation-count delta. Both
OpenBox and native TuRBO backends support continuation.

Per `CONTEXT.md`, a continuation's backend state is *rebuilt from the
accepted evaluation trace*, not resumed from an in-process optimizer object —
so it is not claimed to be bit-for-bit equivalent to one uninterrupted
process. Native TuRBO makes this explicit in its report: a continued run
carries `restore_mode: trace_reconstructed` along with
`continued_from_evaluations` (history size before this continuation) and
`additional_evaluations` (`N`, the evaluations added by this invocation) —
these three fields only appear on a continuation, not a first run.

Continuation cannot be combined with `--dry-orchestration`, and (for OpenBox)
cannot be combined with an enabled **History Warm Start** (below) — the two
history sources are mutually exclusive.

## Remote Preparation Snapshot（远程准备快照，冻结快照）

A remote continuation re-validates the requirement — Doctor re-parses the
current `opt_requirement.md` from the Remote host (see **Continuation**
above) — but it does not re-render the preparation state from that
(possibly edited) requirement. Instead, `prepare_remote_project_cache(...,
frozen_snapshot=True)` restores a previously captured, immutable snapshot of
the preparation state — `CONTEXT.md`'s **Remote Preparation Snapshot** — from
`state/remote_preparation_snapshot` on the Remote host (with up to
`REMOTE_PREPARATION_SNAPSHOT_RETENTION = 3` prior snapshots retained under
`state/remote_preparation_snapshots`, manifested at
`reports/remote_preparation_snapshot.json`). Other shipped docs
(`USER_GUIDE_CN.md`, `AGENT_OPTIMIZER_USAGE_MANUAL.md`, `README.md`,
`skills/ic-opt/SKILL.md`) refer to this informally as the "frozen snapshot";
prefer "Remote Preparation Snapshot" when precision matters, per `CONTEXT.md`.
`frozen_snapshot=True` and `persist_snapshot=True` are mutually exclusive on a
single prepare call — a run either captures a new snapshot or restores a
frozen one, never both. Because a frozen snapshot never carries a supervisor
instruction or preflight reports, restoring one is what forces continuation's
approval path onto the **prior history acceptance** gate described above,
which in turn verifies cumulative history through the checksum-verified
**Remote History Manifest** (`CONTEXT.md`; materialized outside `runs/` by
`materialize_remote_history_manifests`, backed by
`reports/optimizer_run_acceptance_report.json` and
`reports/remote_run_artifacts.sha256`) before any new evaluation is allowed
to run.

## Remote Attempt Lock（远程互斥锁）

Every remote `--real` or `--real --continue N` invocation first claims an
exclusive lock, `state/remote_attempt.lock`, created atomically (`mkdir`)
**inside the Remote project directory** (not the Controller Cache), before
any other Remote-side action. If another Controller already holds it, the
new attempt fails immediately with an error naming the lock directory and
`owner.json` (which records the holding Controller's hostname, PID, SSH
profile, and acquisition time). Locks are **deliberately never stolen
automatically**: recovering from a dead Controller requires an operator to
inspect `owner.json` and manually remove the lock directory on the Remote
host — there is no CLI flag to force-acquire it.

## History Warm Start（历史热启动）

An OpenBox-only, new-project capability (`history_warm_start.yaml`,
`enabled: true` with `sources` and a `topk` warm-start strategy) that seeds
the optimizer's history from prior runs' recorded observations before the
first evaluation. It requires the OpenBox backend and **cannot be combined
with continuation** — enabling it on a project that also passes
`--continue` fails validation. Two of the shipped sanitized templates
(`opt_requirement.multi_testbench.md`, `opt_requirement.history_warm_start.md`)
demonstrate it paired with the `openbox_auto` compatibility strategy (see
[OPTIMIZER_ALGORITHM_MODES.md](OPTIMIZER_ALGORITHM_MODES.md)).

## Artifacts

Workflow acceptance comes from files. Names differ by workflow mode, backend,
and local vs. remote — see
[TOOLCHAIN_EXECUTION_REFERENCE.md](TOOLCHAIN_EXECUTION_REFERENCE.md) for the
authoritative, mode-split list. Summary:

```text
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_flow_run_report.json          (top-level flow status)
reports/optimizer_run_acceptance_report.json    (acceptance decision)
reports/optimizer_run_report.json               (OpenBox backend only)
reports/native_turbo_optimizer_report.json      (native TuRBO backend only)
reports/optimizer_effectiveness_audit.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.json           (also .md, .html)
reports/optimizer_final_summary.json            (also .md)
reports/multi_testbench_aggregation_report.json (multi-testbench/corner only)
reports/fix_run_report.json                     (fix_run workflow only)
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
supervisor_instruction.json                     (project root, not reports/)
```

Multi-testbench and multi-corner runs also write parent aggregate manifests
— see
[PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md](PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md)
for field-level detail. In remote mode, `config/*.yaml` exists only in the
Controller Cache and is never part of what gets published back to
`REMOTE_PROJECT_DIR`.

## Best Observed Result

Optimizer reports identify the best observed feasible candidate under the
configured objective and process-corner policy. This is not a proof of global
optimality.

## Fix-Run Result

Fix-run reports identify whether each requested fixed point and child
testbench/corner completed. They are characterization evidence, not optimizer
recommendations.
