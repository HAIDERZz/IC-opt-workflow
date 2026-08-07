# Remote mode treats filesystem separation as mandatory

Remote mode retains the existing Controller-led optimization architecture, but every Remote-owned Path is accessed only through the configured remote transport. A transport or materialization failure fails closed and never falls back to a same-named Controller path, because shared-path fallback would make correctness depend on an accidental filesystem topology and would conceal defects in the normal personal-PC-to-laboratory-server workflow.

## Consequences

Files may be inspected with Controller filesystem APIs only after the workflow has explicitly materialized them inside the Controller Cache. Self-SSH and shared-NFS runs remain useful smoke tests, but they do not satisfy isolated-filesystem remote acceptance on their own.

Acceptance must use a clean project copy and complete the project's configured optimization budget. A one-evaluation run may detect an immediate transport failure, but it cannot establish that optimizer iteration, batch execution, state persistence, result aggregation, report generation, and remote-to-Controller synchronization work under production conditions.
