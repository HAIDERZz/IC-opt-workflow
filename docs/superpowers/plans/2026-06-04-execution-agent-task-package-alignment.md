# C-22 Execution-Agent Task Package Alignment Plan

## Goal

Align the generated execution package task with the locked role model and the
real C-20/C-21 handoff evidence, without adding a new handoff framework.

## Scope Guard

Allowed:

- update the existing generated `execution_package/EXECUTION_TASK.md` wording;
- remove Claude-specific role naming from the generated task;
- add the manifest-level audit rule learned from C-20;
- keep the existing pre-approval export/package flow unchanged.

Forbidden:

- add a new workflow engine;
- add a new execution-agent service or daemon;
- add new real-tool commands;
- run Virtuoso, Spectre, OCEAN, SSH, or `virtuoso-bridge-lite`;
- change optimizer logic;
- parse PSF or rewrite OCEAN formulas.

## Task 1: Generic Execution-Agent Task Wording

**Status:** Complete, verified-only.

- [x] Change generated task title from Claude-specific wording to generic
  execution-agent wording.
- [x] Add manifest-level audit rule so future real-tool handoffs do not judge
  success from command exit status alone.
- [x] Keep export/preflight responsibilities unchanged.
- [x] Add focused test coverage.
