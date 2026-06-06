# Requirement.md Driven Config Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Let a user-created `opt_requirement.md` plus optional `constraints.md` bootstrap an existing Hermes optimization project by rendering the current YAML contracts and safely importing a Maestro/ADE point-root netlist bundle.

**Architecture:** Keep Markdown intake as the entry interface, but keep existing `config/*.yaml` as the execution source of truth. Add one narrow intake module that parses fixed fenced YAML blocks, renders existing schema-compatible payloads, imports `maestro_point_root/netlist/` into `netlists/exported/`, and delegates validation/template generation to existing commands.

**Tech Stack:** Python 3.11, Typer CLI, PyYAML, existing Pydantic schemas in `src/hermes_workflow/schemas.py`, existing validation and netlist templating in `validate.py` and `netlists.py`.

---

## Scope

C-49 is an intake/bootstrap feature only.

It must not run Virtuoso, Spectre, OCEAN, OpenBox, SSH, or execution agents. It must not parse PSF, rewrite OCEAN formulas, invent sidecar selection rules, replace existing YAML schemas, or change optimizer behavior.

## File Structure

- Create `src/hermes_workflow/requirement_intake.py`
  - Parse `opt_requirement.md` fixed headings and fenced YAML blocks.
  - Render existing config payloads.
  - Safely import `maestro_point_root/netlist/`.
  - Write intake/import reports.
- Modify `src/hermes_workflow/cli.py`
  - Add `check-requirement PROJECT_DIR`.
  - Add `prepare-from-requirement PROJECT_DIR`.
- Create `tests/test_requirement_intake.py`
  - Parser, renderer, importer, and CLI-level smoke coverage.
- Modify `src/hermes_workflow/templates/spectre_maestro_project/`
  - Add example `opt_requirement.md`.
  - Add example `constraints.md`.
- Modify progress docs after implementation is complete:
  - `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
  - `docs/EXECUTION_PROGRESS_2026-05-29.md`
  - `docs/COMPACT_RESUME_CHECKPOINT.md`
  - `docs/CURRENT_TASK_STATE.json`

## User-Facing Commands

```bash
hermes-workflow check-requirement PROJECT_DIR
hermes-workflow prepare-from-requirement PROJECT_DIR
```

`check-requirement` validates Markdown structure, YAML blocks, approval checklist, schema renderability, and Maestro netlist source existence. It writes `reports/requirement_intake_report.json`.

`prepare-from-requirement` runs the same checks, writes `config/*.yaml`, imports the Maestro point-root netlist bundle into `netlists/exported/`, writes `reports/maestro_point_import_report.json`, then calls existing `prepare_netlist(project_dir)` so `netlists/templates/template.scs` is produced by the proven route.

## Task 1: Templates And Fixture Inputs

**Files:**
- Create: `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md`
- Create: `src/hermes_workflow/templates/spectre_maestro_project/constraints.md`
- Create: `tests/fixtures/requirement_intake/valid_project/opt_requirement.md`
- Create: `tests/fixtures/requirement_intake/valid_maestro_point/netlist/input.scs`
- Create: `tests/fixtures/requirement_intake/valid_maestro_point/netlist/ade_e.scs`

- [x] Add a strict example `opt_requirement.md` matching `docs/superpowers/specs/2026-06-05-requirement-md-config-intake-design.md`.
- [x] Use existing inverter metric formulas from the template `config/metrics.yaml`; copy formula text exactly.
- [x] Add a short `constraints.md` that states supervisor guidance only and cannot mutate generated YAML.
- [x] Add fixture `input.scs` with top-level `parameters FN=... WN=... FP=... WP=...`, an `include "ade_e.scs"`, and at least one analysis statement.
- [x] Add a fixture symlink case in the test setup, not in committed files, so tests can create safe and unsafe symlinks under `tmp_path`.
- [x] Verify template project creation still works:

```bash
python3 -m pytest tests/test_package.py -q
```

## Task 2: Markdown Intake Parser And Report

**Files:**
- Create: `src/hermes_workflow/requirement_intake.py`
- Test: `tests/test_requirement_intake.py`

- [x] Write failing tests for:
  - missing `opt_requirement.md`;
  - missing required heading;
  - duplicate required heading;
  - missing fenced YAML block under a required heading;
  - invalid YAML;
  - approval checklist with any value not `true`;
  - `constraints.md` present but ignored for generated contract fields.
- [x] Implement a deterministic parser:
  - accepted headings are exactly the required C-49 headings;
  - one fenced `yaml` block per required section;
  - free prose outside the YAML block is ignored;
  - parsing failures produce a report with `status: fail` and explicit `issues`.
- [x] Define a small return object such as `RequirementIntakeResult` with:
  - `status`;
  - parsed section payloads;
  - `issues`;
  - `constraints_md_present`;
  - `constraints_md_sha256` when present.
- [x] Write `reports/requirement_intake_report.json` for both pass and fail.
- [x] Verify:

```bash
python3 -m pytest tests/test_requirement_intake.py -q
```

## Task 3: Existing YAML Contract Renderer

**Files:**
- Modify: `src/hermes_workflow/requirement_intake.py`
- Test: `tests/test_requirement_intake.py`

- [x] Write failing tests that a valid `opt_requirement.md` renders:
  - `config/project_config.yaml`;
  - `config/variables.yaml`;
  - `config/metrics.yaml`;
  - `config/spectre.yaml`;
  - `config/optimizer.yaml`.
- [x] Render payloads using the existing schema field names exactly:
  - `Project` + `Maestro Source` -> `ProjectConfig`;
  - `Design Variables` -> `VariablesConfig`;
  - `Metrics` + `Constraints` + `Objective` -> `MetricsConfig`;
  - `Spectre Settings` -> `SpectreConfig`;
  - `Optimizer Settings` -> `OptimizerConfig`.
- [x] For each metric, map:
  - `ocean_expression` to `maestro_formula`;
  - `ocean.expression`;
  - `ocean.result`;
  - `ocean.expression_source: user_approved`;
  - `ocean.source_reference: opt_requirement.md`;
  - `ocean.expected_value_type: real_scalar`;
  - `ocean.nil_policy: fail`;
  - `ocean.non_finite_policy: fail`.
- [x] Validate rendered payloads by constructing existing Pydantic schema models before writing files.
- [x] Preserve OCEAN expression strings byte-for-byte from Markdown YAML into generated YAML.
- [x] Verify:

```bash
python3 -m pytest tests/test_requirement_intake.py -q
python3 -m pytest tests/test_validate.py -q
```

## Task 4: Maestro Point-Root Netlist Importer

**Files:**
- Modify: `src/hermes_workflow/requirement_intake.py`
- Test: `tests/test_requirement_intake.py`

- [x] Write failing tests for:
  - missing `maestro_point_root`;
  - missing `maestro_point_root/netlist/input.scs`;
  - safe internal symlink materialized as a regular file;
  - unsafe symlink escaping the Maestro history root rejected;
  - symlink to directory rejected;
  - no symlinks remain under `netlists/exported/`.
- [x] Implement `import_maestro_point_netlist(project_dir, maestro_point_root)`:
  - source root is `maestro_point_root/netlist`;
  - destination is `PROJECT_DIR/netlists/exported`;
  - copy regular files and directories preserving relative layout;
  - materialize safe symlinks as regular files;
  - reject unsafe symlinks before writing a partial destination;
  - write `reports/maestro_point_import_report.json`.
- [x] Include source provenance in the report:
  - `maestro_point_root`;
  - copied file count;
  - materialized symlink count;
  - rejected issue list;
  - `input_scs_sha256`.
- [x] Verify:

```bash
python3 -m pytest tests/test_requirement_intake.py -q
python3 -m pytest tests/test_netlists.py -q
```

## Task 5: CLI Wiring And Local Bootstrap Smoke

**Files:**
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_requirement_intake.py`

- [x] Add `check-requirement PROJECT_DIR`.
  - On pass: print `requirement intake passed`.
  - On fail: print issues, report path, and exit 1.
- [x] Add `prepare-from-requirement PROJECT_DIR`.
  - Parse and validate intake.
  - Write `config/*.yaml`.
  - Import Maestro netlist bundle.
  - Run existing `prepare_netlist(project_dir)`.
  - On pass: print `requirement project preparation passed`.
  - On fail: print issues/report path and exit 1.
- [x] Add CLI tests using `typer.testing.CliRunner`.
- [x] Add one no-real-tool local smoke:

```bash
tmp=$(mktemp -d)
cp -a tests/fixtures/requirement_intake/valid_project/. "$tmp/project"
python3 -m hermes_workflow.cli prepare-from-requirement "$tmp/project"
python3 -m hermes_workflow.cli validate "$tmp/project"
python3 -m hermes_workflow.cli prepare-netlist "$tmp/project"
```

- [x] Verify:

```bash
python3 -m pytest tests/test_requirement_intake.py tests/test_validate.py tests/test_netlists.py -q
```

## Task 6: Final Verification And Progress Sync

**Files:**
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify: `docs/EXECUTION_PROGRESS_2026-05-29.md`
- Modify: `docs/COMPACT_RESUME_CHECKPOINT.md`
- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: this plan checkbox state

- [x] Run targeted verification:

```bash
python3 -m pytest tests/test_requirement_intake.py tests/test_validate.py tests/test_netlists.py -q
```

- [x] Run existing cadence and diff checks:

```bash
python3 -m json.tool docs/CURRENT_TASK_STATE.json
python3 tools/check_development_cadence.py
git diff --check
git status --short
```

- [x] Update progress docs with:
  - C-49 status;
  - exact commands run;
  - confirmation that C-49 is no-real-tool intake/bootstrap only;
  - next step: one focused real bootstrap drill from a user project directory.
- [x] Do not commit raw `input.scs`, Cadence sidecars from protected user paths, PSF/raw data, or full Cadence logs.

## Acceptance Criteria

- A project with only `opt_requirement.md`, optional `constraints.md`, and a `maestro_point_root` path can generate the existing `config/*.yaml`.
- Generated YAML passes existing `hermes-workflow validate`.
- The full Maestro netlist bundle is imported without requiring user sidecar selection.
- Safe symlinks are materialized; unsafe symlinks fail closed.
- Existing `prepare-netlist` can produce `netlists/templates/template.scs`.
- No real EDA tool is invoked by C-49.

## Route Audit

- **Active spec:** `docs/superpowers/specs/2026-06-05-requirement-md-config-intake-design.md`
- **Top-level plan:** `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- **Alignment:** This plan fills the user-intake gap while preserving the proven Spectre/OCEAN/OpenBox execution route and the existing YAML contracts.
- **Drift:** No drift. This plan does not change optimizer logic, run real tools, parse PSF, rewrite OCEAN formulas, or flatten the Maestro/ADE netlist layout.
