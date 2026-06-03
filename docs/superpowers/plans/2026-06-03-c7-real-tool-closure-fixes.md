# C-7 Real Tool Closure Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for planned fix tasks. During the fast debug lane, use superpowers:systematic-debugging first, keep each fix surgical, and stop after each task for evidence review.

**Goal:** Make the real C-12/C-7 Spectre + OCEAN closed loop pass once, without adding new optimizer features.

**Architecture:** Fix only the automation contract gaps exposed by real tools: Spectre invocation compatibility, exported netlist sidecars, Spectre-safe parameter rendering, and ADE-style `netlist/` working-directory layout for OCEAN name recovery. Hermes still validates contracts and records only checked OCEAN-produced scalar results; Python must not parse PSF or rewrite Calculator/OCEAN formulas.

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

## Task 3: ADE Netlist/PSF Layout Contract

**Files:**
- Modify: `src/hermes_workflow/real_run.py`
- Modify: `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Modify: real-run/result/recovery contract checks affected by the rendered input path
- Test: real-run package, adapter, result handoff, metric result, and retry tests

- [x] **Step 1: Compare broken adapter output against the successful Phase4 evidence**
  - Confirmed the formulas are not the root cause.
  - Confirmed `runs/real/<id>/psf` generated from a flattened run directory exposes plain OCEAN names and fails slash formulas.
  - Confirmed `parent/netlist` as Spectre cwd with sibling `parent/psf` restores slash names such as `/VOUT`, `/VDD`, and `/M0/S`.

- [x] **Step 2: Encode the layout in contracts**
  - Prepared real-run input is now `runs/real/<id>/netlist/input.scs`.
  - Exported Maestro sidecars are copied into `runs/real/<id>/netlist/`.
  - Spectre runs from `runs/real/<id>/netlist` and writes PSF to sibling `runs/real/<id>/psf`.
  - Metric formulas remain user/project-approved OCEAN expressions; no namespace rewriting was added.

- [x] **Step 3: Verify**
  - Run focused metric request/OCEAN script tests.
  - Run: `python3 -m pytest tests/test_real_run.py tests/test_spectre_ocean_adapter.py tests/test_metric_results.py tests/test_result_handoff.py tests/test_real_run_recovery.py tests/test_next_real_run.py tests/test_cli.py -q`
  - Result: `248 passed`.
  - Run: `python3 -m pytest -q`
  - Result: `445 passed`.
  - Run: `python3 -m ruff check .`
  - Result: `All checks passed!`.

## Task 4: Real Closure Smoke

**Files:**
- Modify only docs/progress files unless a new root cause is found.
- Evidence: local-only `/tmp` transcripts and sanitized `docs/debug/` note.

- [x] **Step 1: Prepare one approved real run**
  - Use the existing C-12 one-cell scope.

- [x] **Step 2: Run the C-7 adapter once**
  - Expected: Spectre succeeds, OCEAN succeeds, and `metric_result_manifest.json` is produced.

- [x] **Step 3: Run Hermes checks and record**
  - Expected: `check-real-run`, `check-metric-results`, and `record-real-result` all pass.

- [x] **Step 4: Record closure evidence**
  - Temporary project: `/tmp/ic_auto_opt_c7_fixed_001/bridge_test_inv`
  - Adapter result: `succeeded: run_id=real_001`
  - Metrics:
    - `rise = 7.52016846017672e-11 s`
    - `fall = 1.078998721053984e-10 s`
    - `DC = 0.0002588877964196586 W`
  - Hermes checks: `check-real-run`, `check-metric-results`, and `record-real-result` passed.

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
