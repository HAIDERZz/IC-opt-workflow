# 0001: Remote mode treats filesystem separation as mandatory

- **Status**: Accepted
- **Date**: 2026-08-07 (introduced with commit `af42dde` (release repo;
  development repo `b4127f8`), "fix(remote): support isolated controller
  filesystems")

## Context

Remote mode drives real Spectre/OCEAN/optimizer execution on a laboratory
Linux EDA server (the Remote host) from a separate personal-PC-class machine
(the Controller), coordinated over an OpenSSH transport
(`--ssh-profile PROFILE`). Under self-SSH or a shared-NFS mount, a
Controller-side code path that (even accidentally) reads a Remote-owned path
directly off the Controller's own local filesystem can still produce the
right bytes, because the same path string happens to resolve to the same
file on both machines under those topologies. That accident is exactly the
opposite of the normal personal-PC-to-laboratory-server topology this
product targets, where the Controller and Remote do **not** share a
filesystem. Any code path that relied on that accident — even implicitly,
even only as a fallback — would silently produce wrong results, or silently
succeed when the transport had actually failed, the first time it ran
against a genuinely isolated Remote host.

Terminology used throughout this ADR (`Controller`, `Remote Host`,
`Controller Cache`, `Remote-owned Path`, `Materialized Artifact`) is defined
in `CONTEXT.md` at the release root; this ADR predates that glossary as a
standalone document but is consistent with it.

## Decision

- Every Remote-owned Path (any path whose authority is the Remote host —
  `opt_requirement.md`, `config/`, `reports/`, `runs/`, `ledger/`, `state/`,
  the Cadence cshrc, netlists, model files) is accessed **only** through the
  configured remote transport (SSH), or after being explicitly
  **materialized** into the Controller Cache. Controller-side code must
  never infer a Remote-owned path's existence or contents from a same-named
  path on the Controller's local filesystem.
- A transport or materialization failure **fails closed**: it is surfaced as
  an error, never silently downgraded to "file missing" and never used as a
  trigger to fall back to a same-named Controller path.
- There is **no same-named-path fallback**, ever — even in a case where it
  would happen to produce the correct answer under a shared-filesystem
  topology (self-SSH, shared NFS). Shared-path fallback would make
  correctness depend on an accidental filesystem topology and would conceal
  defects in the normal, non-shared personal-PC-to-laboratory-server
  workflow.

Concretely, in the SSH existence-probe implementation this means: an SSH
`test -f` returning exit status `0` means "exists", `1` means "does not
exist", and *any other* exit status (transport failure, auth failure,
timeout) must be surfaced as a transport/probe error. It must not be treated
as "the file is missing", and it must not trigger a check of the
Controller's own filesystem for a path with the same name.

## Consequences

- Files may be inspected with Controller filesystem APIs only after the
  workflow has explicitly materialized them inside the **Controller Cache**,
  at
  `~/.ic-opt/remote_runs/<ssh_profile>/<sha256(f"{ssh_profile}\n{remote_project_dir}")[:16]>`
  (`remote_project.py`: `DEFAULT_REMOTE_CACHE_ROOT`, `remote_cache_dir`). The
  cache key hashes both the SSH profile name and the Remote project
  directory, so distinct `(profile, remote path)` pairs never collide into
  the same cache directory.
- The Controller Cache is **not a persistent workspace**: every call to
  `prepare_remote_project_cache` unconditionally deletes any pre-existing
  cache directory for that key (`shutil.rmtree`, `remote_prepare.py:107-111`)
  before doing anything else. `frozen_snapshot=True` does not skip that
  deletion; it only changes what repopulates the now-empty cache directory
  afterward — restoring a Remote Preparation Snapshot for a continuation
  instead of rebuilding from scratch (see `docs/ROLE_MODEL_AND_TERMINOLOGY.md`,
  "Remote Preparation Snapshot"). Do not rely on the Controller Cache to
  retain results between independent `--real` invocations — it is a
  disposable, explicitly-materialized representation of Remote-owned state,
  never the authority for it.
- `config/*.yaml` in particular is written **only** into the Controller
  Cache during preparation and is never synced back to the Remote project:
  `remote_optimizer_flow.py`'s `_sync_cache_reports_to_remote` publishes only
  `ledger/`, `state/`, `execution_package/`, and `reports/`, plus the parent
  run manifest. A `REMOTE_PROJECT_DIR/config/optimizer.yaml` does not exist
  after a remote run — see
  `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`, "Real Workflow Evidence".
- Self-SSH and shared-NFS runs remain useful smoke tests (they exercise the
  transport code path end to end), but they do not satisfy isolated-filesystem
  remote acceptance on their own, because a same-named-path bug would not
  produce an observable failure under those topologies.
- Acceptance must use a clean project copy and complete the project's
  configured optimization budget. A one-evaluation run may detect an
  immediate transport failure, but it cannot establish that optimizer
  iteration, batch execution, state persistence, result aggregation, report
  generation, and remote-to-Controller synchronization work under production
  conditions.

### Acceptance benchmark

The real acceptance run exercised against this rule is recorded in
`docs/audits/2026-08-10-real-world-correctness-audit-and-repair-ledger-cn.md`,
§13.4 ("隔离 Remote 真实工程验收", dated 2026-08-10): an isolated 32 GiB
Remote-only tmpfs mount namespace, 3 testbenches × 3 process corners × 100
candidates (900 real Spectre/OCEAN sub-simulations), a Controller-side
existence check and a Remote-side SSH existence check on the *same*
`opt_requirement.md` path returning opposite results (proving genuine
filesystem isolation rather than a shared path posing as one), and a
2200-artifact Controller/Remote SHA-256 cross-check with zero mismatches.
Treat that acceptance run — not a one-evaluation smoke test, and not a
self-SSH or shared-NFS run — as the bar for validating a future change to
this boundary.

## Alternatives Considered

- **Shared-path fallback** (treat a same-named Controller path as
  authoritative when the transport is slow or briefly unavailable): rejected
  because it reintroduces exactly the failure mode this ADR exists to close
  — correctness would then depend on whichever filesystem topology the
  Controller happens to run on, and a defect that only shows up on a
  genuinely isolated Remote host would pass silently under self-SSH or
  shared-NFS development and CI.
- **Treat self-SSH / shared-NFS as sufficient acceptance evidence**: rejected
  for the same reason — those topologies cannot distinguish "the transport
  correctly fetched Remote-owned content" from "the Controller happened to
  already have the same bytes locally". The acceptance benchmark above
  deliberately uses an isolated mount namespace so a same-path fallback bug
  cannot pass by accident.
- **Degrade an ambiguous SSH probe result (a non-`0`/`1` exit status) to
  "file missing"**: rejected because it would make a transport outage
  indistinguishable from a genuinely absent file, silently corrupting
  doctor/preflight checks; such results must fail closed as transport
  errors instead.

## Related Decisions (not written this round)

The following are ADR-level decisions already embedded in the current
implementation but not yet split into their own ADR files. They are
recorded here as pending documentation debt, not as new
`docs/adr/0002-*.md` / `0003-*.md` files, so a future pass can decide how to
scope and title them:

- **Continuation restores a frozen Remote Preparation Snapshot.** A remote
  continuation does not re-resolve `opt_requirement.md` from the Remote host;
  it restores a previously captured, immutable snapshot
  (`remote_prepare.py`, `frozen_snapshot=True`, mutually exclusive with
  `persist_snapshot=True` on the same prepare call), and its approval path
  substitutes prior-history acceptance for preflight readiness (see
  `docs/ROLE_MODEL_AND_TERMINOLOGY.md`, "Supervisor Instruction" and "Remote
  Preparation Snapshot").
- **Remote attempts are serialized by a lock that is never auto-stolen.**
  `remote_attempt_lock.py` claims `state/remote_attempt.lock` on the Remote
  host with an atomic `mkdir`; per its docstring, "Locks are deliberately
  never stolen automatically. If a Controller dies, the owner metadata tells
  the operator what to inspect before manually removing the lock directory."
  (see `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`, "Remote Attempt Lock").
- **Only Remote-owned artifacts are published back, and the flow report
  publishes last.** `_sync_cache_reports_to_remote` publishes `ledger/`,
  `state/`, `execution_package/`, and `reports/` (excluding the flow report
  itself) from the Controller Cache to the Remote project, then uploads
  `reports/optimizer_flow_run_report.json` last — so its presence on the
  Remote host is the signal that the rest of that run's evidence already
  landed. `config/` is never part of this publication set. A parallel path,
  `_sync_failure_evidence_to_remote`, refuses to publish a report whose
  `status` is not `"fail"` as failure evidence, so a partial or aborted run
  cannot masquerade as a completed failure report.
