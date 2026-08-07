# Remote IC Optimization

This context describes how a user-controlled machine coordinates IC optimization on a laboratory server whose filesystem and EDA environment are independent.

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

**Remote Acceptance Run**:
A clean, production-scale optimization run in which the Controller cannot access Remote-owned Paths directly, the project-configured evaluation budget is completed, and remote execution, result materialization, optimizer state, aggregation, and final reports are all verified.
_Avoid_: One-evaluation smoke test, self-SSH acceptance
