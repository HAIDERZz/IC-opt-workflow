# Netlist Template Contract Design

## Goal

Add a Hermes-side netlist preparation step that converts a Maestro-exported Spectre `input.scs` into a safe `template.scs` by templating only approved top-level parameter values. This establishes the first real bridge between the YAML variable contract and the Spectre deck contract without running Spectre or changing the Maestro setup.

## Scope

Included:

- A lightweight Spectre parameter templater for exported decks.
- Reading project config and variable whitelist through the existing validated contract.
- Generating `netlists/templates/template.scs` from `netlists/exported/input.scs`.
- Writing `reports/netlist_preparation_report.json` using the existing `NetlistPreparationReport` schema.
- A CLI command for the netlist preparation step.
- Unit tests with repository-local, hand-written, sanitized Spectre fixtures.
- Manual validation against local-only real examples under `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example`.

Excluded:

- Committing real Virtuoso-exported `input.scs` examples.
- Parsing or executing Maestro calculator formulas.
- Running Spectre, Virtuoso, or the optimizer.
- Rewriting device, subckt, source, analysis, include, or model statements.
- Inferring optimization variables from arbitrary token usage in the deck.
- Supporting multi-file netlist include rewriting.

## Real Example Policy

The four real `input.scs` examples in `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/netlist_example` are local reference material only. They must not be copied into the repository, committed as fixtures, or included in generated documentation.

Repository tests will use small sanitized Spectre snippets that preserve the structural cases found in the real examples:

- Single-line top-level `parameters` statements.
- Backslash-continued top-level `parameters` blocks.
- Variables referenced later by device expressions such as `w=WP*FP`.
- Large decks with subckt, include, source, analysis, and save statements that must remain unchanged.

## Architecture

Add a focused module, `src/hermes_workflow/netlists.py`, that owns Spectre netlist template generation. The module reads the already-validated project bundle, loads the exported deck as text, rewrites only approved assignments in top-level `parameters` statements, writes the template deck, and returns a `NetlistPreparationReport`.

The implementation intentionally avoids a full Spectre parser. It uses a conservative line-oriented scanner that recognizes `parameters` statements only when the logical statement starts at top level with the token `parameters`. Continuation lines ending in `\` are merged as one logical statement for detection and rewriting, then written back with the original line structure preserved as much as possible.

`cli.py` will expose this through a command named `prepare-netlist`, following the existing pattern where CLI commands delegate business logic to a module and only format success or error output.

## Template Placeholder Contract

Approved variable assignments are rewritten to Jinja-style placeholders:

```spectre
parameters temperature=27 FN=4 FP=4 WN=0.6u WP=1.2u
```

becomes:

```spectre
parameters temperature=27 FN={{FN}} FP={{FP}} WN={{WN}} WP={{WP}}
```

The placeholder spelling is exactly `{{VARIABLE_NAME}}`, with no spaces inside the braces. This keeps the rendered candidate contract simple and lets later dry-run checks detect unresolved placeholders with a deterministic string pattern.

Only the right-hand side of a whitelisted assignment may change. Later references remain untouched:

```spectre
M0 (VOUT IN VSS VSS) nmos w=WN*FN l=45n
```

## Parameter Detection Rules

The templater recognizes parameter definitions with these rules:

- A logical statement is eligible only if its first non-whitespace token is `parameters`.
- Continuation lines ending in `\` are part of the same logical statement.
- Assignments are recognized as `NAME=VALUE`, where `NAME` must match the existing variable-name contract `[A-Za-z_][A-Za-z0-9_]*`.
- The value extends until the next whitespace-delimited assignment token or the end of the logical statement.
- Comments and non-parameter statements are copied unchanged.
- Subckt pins, instance parameters, analysis options, save statements, includes, and model statements are never eligible for templating.

The MVP expects simple Spectre parameter assignment syntax. If a value shape cannot be rewritten without ambiguity, the templater fails closed and writes a fail report instead of guessing.

## Error Handling

`prepare_netlist(project_dir)` should always write a `netlist_preparation_report.json` when it can load enough project context to locate the reports directory.

Pass conditions:

- The exported `input.scs` exists.
- Every approved variable from `variables.yaml` is found exactly once in eligible top-level parameter assignments.
- No approved variable requires modifying text outside eligible parameter assignments.
- `template.scs` is written successfully.
- No forbidden setup changes are detected.

Fail conditions:

- Exported `input.scs` is missing.
- An approved variable is missing from eligible parameter assignments.
- An approved variable appears more than once in eligible parameter assignments.
- The `parameters` statement cannot be parsed conservatively.
- The output path is outside the configured project-relative `netlists/templates/` location.
- File writing fails.

Failures set:

- `status` to `fail`.
- `approved_variables_template_status[variable]` to `false` for variables that were not safely templated.
- `forbidden_setup_changes_detected` to `true` only if the templater detects that it would need to alter non-parameter setup text.
- `issues` to human-readable messages that can be surfaced by the existing approval gate.

## Report Contract

The netlist preparation step writes the existing report shape:

```json
{
  "schema_version": "1.0",
  "status": "pass",
  "exported_input_scs": "netlists/exported/input.scs",
  "template_scs": "netlists/templates/template.scs",
  "approved_variables_template_status": {
    "FN": true,
    "WN": true,
    "FP": true,
    "WP": true
  },
  "analysis_statements": ["tran", "dcOp"],
  "forbidden_setup_changes_detected": false,
  "issues": []
}
```

`analysis_statements` records top-level analysis statement names detected in the deck, such as `tran`, `dc`, `dcOp`, `ac`, `pss`, `pac`, or `pnoise`. This is informational for review and approval; the templater does not validate analysis semantics.

## Data Flow

1. User or upstream bridge exports the Maestro deck to `netlists/exported/input.scs`.
2. Hermes validates the project YAML bundle through the existing `assert_valid_project()` boundary.
3. `prepare_netlist(project_dir)` reads the configured exported and template paths from `project_config.yaml`.
4. The templater scans the exported deck and rewrites only approved parameter assignment values.
5. Hermes writes `netlists/templates/template.scs`.
6. Hermes writes `reports/netlist_preparation_report.json`.
7. Existing preflight loading and approval logic consumes the report unchanged.

## CLI Contract

Add:

```bash
hermes-workflow prepare-netlist PROJECT_DIR
```

Success output should be concise and machine-stable enough for smoke tests:

```text
netlist preparation passed
```

Failure should exit non-zero and print the report issues. If a fail report was written, the CLI should mention its path.

## Testing

Tests should live in `tests/test_netlists.py`.

Required coverage:

- Single-line `parameters` statement templates only approved RHS values.
- Backslash-continued `parameters` block templates approved RHS values.
- Device expressions and later variable references are not rewritten.
- Missing approved variables produce a fail report.
- Duplicate approved parameter definitions produce a fail report.
- Analysis statement names are reported without validating their contents.
- CLI smoke test for `prepare-netlist` succeeds on a sanitized fixture.

No unit test may depend on real Virtuoso decks, Spectre, network access, Claude CLI, or the local-only `netlist_example` directory.

## Acceptance Criteria

- `prepare_netlist(project_dir)` generates `template.scs` and `netlist_preparation_report.json`.
- The generated template changes only approved top-level parameter assignment RHS values.
- The report validates with the existing `NetlistPreparationReport` model.
- The CLI exposes `prepare-netlist`.
- The full test suite passes.
- `ruff check .` passes.
- Real `input.scs` examples remain untracked and outside the repository.
