# C-7 Real Tool Closure Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for planned fix tasks. During the fast debug lane, use superpowers:systematic-debugging first, keep each fix surgical, and stop after each task for evidence review.

**Goal:** Make the real C-12/C-7 Spectre + OCEAN closed loop pass once, without adding new optimizer features.

**Architecture:** Fix only the automation contract gaps exposed by real tools: Spectre invocation compatibility, exported netlist sidecars, Spectre-safe parameter rendering, and OCEAN formula namespace alignment. Hermes still validates contracts and records only checked OCEAN-produced scalar results; Python must not parse PSF or rewrite Calculator/OCEAN formulas.

**Tech Stack:** Python, Typer CLI, Pydantic schemas, Spectre command adapter, OCEAN script generation, pytest.

---

## Scope Lock

The `=log` Spectre command compatibility fix is already committed as `51fc057`.

## Task 0: Real Tool Evidence Inventory

**Status:** Complete, verified-only.

**Files:**
- Local-only bundle: `/tmp/ic_auto_opt_real_tool_evidence/`
- Repo index: `docs/debug/2026-06-03-real-tool-evidence-index.md`

- [x] **Step 1: Collect existing evidence without rerunning real tools**
  - Copied inverter Spectre/OCEAN smoke evidence.
  - Copied mixer PSS/PAC OCEAN probe evidence.
  - Copied C-7 adapter debug contexts.
  - Copied C-12 controlled real-tool practice evidence.

- [x] **Step 2: Generate local file inventory and hashes**
  - Local file tree: `/tmp/ic_auto_opt_real_tool_evidence/manifests/file_tree.txt`
  - Local hashes: `/tmp/ic_auto_opt_real_tool_evidence/manifests/hashes.sha256`

- [x] **Step 3: Write sanitized repo index**
  - Repo file: `docs/debug/2026-06-03-real-tool-evidence-index.md`
  - The index records evidence categories, conclusions, local paths, and commit boundaries.

This plan must not:

- add new optimizer strategy;
- bypass Hermes check/record contracts;
- manually repair manifests to make a failed run pass;
- parse PSF in Python;
- translate or reimplement metric formulas in Python;
- commit raw `input.scs`, protected include files, PSF/raw data, full Cadence logs, `docs/OCEAN_DOC_*`, or `docs/toolchain_evidence/`.

## Task 1: Exported Netlist Bundle Sidecars

**Status:** Complete, verified-only.

**Files:**
- Modify: `src/hermes_workflow/package.py`
- Modify: `src/hermes_workflow/real_run.py`
- Test: existing package/real-run tests that cover netlist export copying

- [x] **Step 1: Add a failing test**
  - Create a fixture project whose `netlists/exported/input.scs` contains `include "ade_e.scs"` and whose export directory contains `ade_e.scs`.
  - Expected before fix: the prepared real-run directory contains only `input.scs`.

- [x] **Step 2: Preserve the exported netlist bundle**
  - Copy safe regular files from `netlists/exported/` into the prepared real-run directory alongside `input.scs`.
  - Reject symlinks, absolute paths, path traversal, and missing include sidecars.

- [x] **Step 3: Verify**
  - Run: `python3 -m pytest tests -q`
  - Run: `python3 -m ruff check src tests tools`
  - Run: `git diff --check`

## Task 2: Spectre-Safe Unit Formatting Guard

**Status:** Complete, verified-only.

**Files:**
- Modify: `src/hermes_workflow/validate.py`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/config/variables.yaml`
- Test: variable validation tests

- [x] **Step 1: Add a failing test**
  - Use a variable value such as `"0.3 um"` and assert validation rejects it with a clear error.

- [x] **Step 2: Make shipped template values Spectre-safe**
  - Replace whitespace-separated units with compact Spectre suffixes such as `0.3u`, `3u`, and `0.2u`.
  - Keep user intent unchanged.

- [x] **Step 3: Verify**
  - Run focused validation/template tests.
  - Run: `python3 -m pytest tests -q`
  - Run: `python3 -m ruff check src tests tools`
  - Run: `git diff --check`

## Task 3: Metric Namespace Contract

**Files:**
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/config/metrics.yaml`
- Modify: metric request generation or validation only if needed
- Test: metric request generation and OCEAN script generation tests

- [ ] **Step 1: Decide formula source**
  - Use user/project-approved formulas that match the actual standalone OCEAN result namespace, or preserve a proven Maestro mapping context.
  - Do not translate formulas automatically.

- [ ] **Step 2: Encode the decision in contracts**
  - Record whether each metric formula is `standalone_ocean` or `maestro_namespace`.
  - Fail closed when the active backend cannot support the declared namespace.

- [ ] **Step 3: Verify**
  - Run focused metric request/OCEAN script tests.
  - Run: `python3 -m pytest tests -q`
  - Run: `python3 -m ruff check src tests tools`
  - Run: `git diff --check`

## Task 4: Real Closure Smoke

**Files:**
- Modify only docs/progress files unless a new root cause is found.
- Evidence: local-only `/tmp` transcripts and sanitized `docs/debug/` note.

- [ ] **Step 1: Prepare one approved real run**
  - Use the existing C-12 one-cell scope.

- [ ] **Step 2: Run the C-7 adapter once**
  - Expected: Spectre succeeds, OCEAN succeeds, and `metric_result_manifest.json` is produced.

- [ ] **Step 3: Run Hermes checks and record**
  - Expected: `check-real-run`, `check-metric-results`, and `record-real-result` all pass.

- [ ] **Step 4: Record closure evidence**
  - Write a sanitized debug note.
  - Update progress files and stop for user review.

## Success Criteria

The real closure is not complete until this exact chain succeeds:

```text
Hermes prepare-real-run
-> C-7 adapter runs Spectre
-> C-7 adapter runs OCEAN
-> metric_result_manifest.json status is succeeded
-> Hermes check-real-run passes
-> Hermes check-metric-results passes
-> Hermes record-real-result passes
```
