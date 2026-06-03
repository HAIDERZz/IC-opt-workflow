# Lightweight Process Hardening Cadence Design

Date: 2026-06-03

Current scope: Plan C process hardening lightweight cadence guard

## Purpose

This design adds a small, mechanical guard against task-node drift after context
compaction. It does not change Hermes workflow contracts, does not run real
EDA tools, and does not add a large process layer.

The required shape is:

- one written spec for the guard itself
- one checker under 200 lines
- one current-state JSON file used as the resume anchor

## Problem

The previous cadence relied on prose spread across progress files. After long
sessions or context compaction, the active node could drift from the top-level
plan, and the word `reviewed` could be recorded even when no true fresh-role
subagent review had run.

This guard makes the active state explicit and machine-checkable. It does not
try to validate all historical docs. It validates the current node that the next
agent should trust.

## Status Vocabulary

- `verified-only`: local verification commands passed, but no true independent
  subagent or explicit review evidence is available.
- `reviewed`: reserved for a task with recorded spec-review and code-quality
  review evidence.
- `blocked-no-subagent`: work cannot honestly proceed under a plan that requires
  subagents because no callable subagent dispatch path is available.

If no callable subagent dispatcher is available, new task state must use
`verified-only` or `blocked-no-subagent`, not `reviewed`.

## Current State Contract

`docs/CURRENT_TASK_STATE.json` is the canonical resume entry after context
compaction. It records:

- the current scope and status
- the active spec and top-level plan paths
- progress files that must mention the current scope and next action
- the review status and review evidence
- forbidden actions for the current boundary
- required pre-commit checks

The JSON is deliberately small. It should point to authoritative docs instead
of duplicating long plans.

## Checker Contract

`tools/check_development_cadence.py` must:

- stay at or below 200 lines
- use only the Python standard library
- load and validate `docs/CURRENT_TASK_STATE.json`
- confirm referenced spec, top-level plan, and progress files exist
- confirm the active spec mentions the current scope
- confirm progress files mention the current scope and next allowed action
- reject `reviewed` status without review evidence
- reject current-status lines that say `reviewed` while the JSON says
  `verified-only` or `blocked-no-subagent`
- reject staged `docs/OCEAN_DOC_*` and `docs/toolchain_evidence/` paths

The checker is intentionally narrow. It guards the current node and high-risk
staging mistakes; it is not a general Markdown linter.

## Boundaries

This process-hardening task must not:

- run Virtuoso
- run Spectre
- run OCEAN
- run SSH
- run Claude CLI
- run `virtuoso-bridge-lite`
- use network access
- run the subprocess-backed C-7 adapter
- parse PSF data
- rewrite OCEAN formulas
- stage `docs/OCEAN_DOC_*`
- stage `docs/toolchain_evidence/`

## Acceptance Criteria

- A failing checker test is run before the checker exists or passes.
- `tests/test_development_cadence_checker.py` covers accepted `verified-only`
  state and rejection of false `reviewed` state.
- `tools/check_development_cadence.py` passes the tests and remains under 200
  lines.
- `docs/CURRENT_TASK_STATE.json` points to this spec, the top-level plan, and
  the current progress files.
- `AGENTS.md` requires the current-state JSON and checker in the cadence.
- Progress and compact-resume docs identify this hardening node as
  `verified-only`.
- Focused pytest, ruff, the cadence checker, `git diff --check`, and line-count
  verification pass before commit.
