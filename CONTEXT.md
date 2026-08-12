# Remote IC Optimization

This context describes how a user-controlled machine coordinates IC optimization on a laboratory server whose filesystem and EDA environment are independent.

Scope: this file is the remote-mode terminology glossary only. For the
User/Agent/CLI role model and non-remote vocabulary, see
`docs/ROLE_MODEL_AND_TERMINOLOGY.md`.

## Language

**Controller**:
The user's machine that owns the optimization session and coordinates work performed on a Remote Host.
_Avoid_: Local host, client

**Remote Host**:
The laboratory server that owns the EDA environment and performs simulation work for a Controller.
_Avoid_: Backend, worker

**Controller Cache**:
A disposable Controller-side representation of explicitly transferred remote project state; it is never the authority for Remote-owned Paths.
_Avoid_: Local project, remote project

**Remote-owned Path**:
A path whose authority is the Remote Host and whose existence or contents must not be inferred from the Controller filesystem.
_Avoid_: Shared path, local path

**Materialized Artifact**:
Remote-owned content explicitly transferred into the Controller Cache and represented there by a Controller-owned path.
_Avoid_: Mirrored path, shared file

**Remote Preparation Snapshot**:
The frozen set of Materialized Artifacts and validated requirement state consumed by one remote optimization run.
_Avoid_: Live remote project, shared working tree

**Remote Mode**:
An optimization workflow coordinated by a Controller and executed against a Remote Host, with filesystem separation treated as the normal case.
_Avoid_: Local mode over SSH, shared-filesystem mode

**Remote Attempt Lock**:
A token-owned lock at `state/remote_attempt.lock` on the Remote Host that allows only one active Controller attempt against a given Remote project at a time. A Controller rejected because the lock is held must inspect the recorded owner before manually removing a stale lock.
_Avoid_: File lock, session token

**Continuation (Trace-Reconstructed State)**:
Extending an existing optimizer project by a requested number of additional evaluations without rereading `opt_requirement.md`. The active backend state is rebuilt from the accepted evaluation trace rather than resumed from in-process memory, so reports record `restore_mode: trace_reconstructed` instead of claiming bit-for-bit equivalence to one uninterrupted process.
_Avoid_: Resume, restart, bit-for-bit replay

**Remote History Manifest**:
The checksum-verified set of prior parent run manifests that a Remote continuation or acceptance run materializes outside `runs/` to validate cumulative history before appending new evaluations.
_Avoid_: Run log, history file

**Remote Acceptance Run**:
A clean, production-scale optimization run in which the Controller cannot access Remote-owned Paths directly; either the project-configured evaluation budget is completed, or an audited Continuation increment is completed and its cumulative history passes verification through the Remote History Manifest; and remote execution, result materialization, optimizer state, aggregation, and final reports are all verified.
_Avoid_: One-evaluation smoke test, self-SSH acceptance

`Remote Preparation Snapshot` and `Remote Acceptance Run` are currently
defined only in this file; other docs refer to the same ideas informally
(for example "frozen snapshot", "production-scale run") rather than by this
exact term. Prefer the term above over an informal paraphrase when writing
about remote mode elsewhere.
