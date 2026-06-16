# C-73 Doctor Requirement Semantic Checks Design

Date: 2026-06-12

## Decision

Strengthen `ic-opt PROJECT --doctor` and
`ic-opt --ssh-profile PROFILE PROJECT --doctor` so deterministic
`opt_requirement.md` mistakes are caught by tooling before any real
Spectre/OCEAN/OpenBox work starts.

This is a product-hardening task, not a new optimizer backend. The goal is to
reduce first-run failure rate for human users and agent operators.

## Product Principle

Doctor owns structural and semantic checks that can be evaluated
deterministically. Agents own explanation, triage, and engineering judgement.

Do not move deterministic requirement validation into prompt instructions only.
The same requirement file must produce the same doctor result whether a human,
Codex, Claude, OpenCode, or any other shell-capable agent runs it.

## Hermes Meaning

In this product, Hermes is the requirement-to-execution messenger layer. It
translates a human IC optimization request from `opt_requirement.md` into
executable, auditable contracts and reports.

Hermes is not a required controlling agent. The user-facing and agent-facing
entrypoint is `ic-opt`.

## Current State

Existing code already checks:

- required Markdown sections;
- exactly one fenced YAML block per required section;
- duplicate YAML mapping keys;
- approval checklist values;
- required fields via config rendering;
- Pydantic schema validation for rendered YAML payloads;
- duplicate metric names through `MetricsConfig`;
- multi-testbench metric route declarations;
- `maestro_point_root/netlist/input.scs` existence, locally or over SSH.

Missing doctor-level checks:

- Objective expression references undefined metric names.
- Objective expression uses only supported function/operator names.
- Objective expression can be evaluated on a dummy finite metric dictionary.
- Constraint metric names are defined in the Metrics section.
- Metric names that differ only by case or common spelling style are warned
  early, especially `P1DB` versus `P1dB`.
- Design variable names are unique and do not collide with metric names in a
  way that makes formulas ambiguous.
- Design variable bounds/steps are semantically valid beyond schema shape.
- Remote runs with excessive `parallel_jobs` warn before SSH stress failures.

## Scope

Add a semantic validation layer to requirement intake.

The layer should be used by:

- local `check_requirement`;
- local `prepare_from_requirement`;
- product-level local `ic-opt --doctor` through the existing flow;
- remote `run_remote_doctor` through `parse_requirement_text`.

The first implementation should keep the public report shape backward
compatible by preserving `RequirementIntakeReport.status`, `issues`, and
`sections`. It may add `warnings` only if the implementation can do so without
breaking existing tests or consumers; otherwise warning-like findings can be
encoded as non-fatal report fields in a narrow compatible way.

## Non-Goals

- Do not run Spectre, OCEAN, OpenBox, or SSH stress tests.
- Do not evaluate real OCEAN formulas.
- Do not rewrite user OCEAN formulas.
- Do not rewrite objective expressions.
- Do not parse PSF/waveform databases.
- Do not try to prove objective quality.
- Do not replace agent guidance. Agents still explain doctor output.
- Do not introduce a TUI.

## Requirement Semantic Checks

### Objective Metric Reference Check

Given:

```yaml
Metrics:
- name: BW
- name: MAX_GAIN

Objective:
  expression: "-(BW + NF_3G)"
```

Doctor must fail with an actionable issue:

```text
objective expression references unknown metric NF_3G
```

The checker must detect metric identifiers used in the objective expression and
compare them against declared metric names.

Allowed non-metric symbols include supported numeric functions and constants.
Initial supported names:

```text
min, max, abs, ln, log, log10, exp, sqrt, pow
```

Numeric constants and scientific notation must be accepted.

### Objective Dummy Evaluation Check

Doctor should evaluate the objective expression with a dummy metric dictionary
where each declared metric is assigned a finite positive value. This catches
syntax, unsupported symbols, unsafe constructs, and obvious evaluation errors
without needing simulation.

Examples that must fail:

```text
BW +
eval("1")
__import__("os").system("rm -rf /")
unknown_func(BW)
BW / 0
```

Examples that must pass:

```text
power / (rise + fall)
-(0.7*min(max(0,min(1,(MAX_GAIN-5)/1)), max(0,min(1,(10-NF_3G)/0.5))))
10*(ln(BW/28e9)/ln(10))/0.6
```

The evaluator must be safe. Prefer an AST whitelist over Python `eval`.

### Constraint Metric Check

Every constraint `metric` must exist in the Metrics section.

Failure example:

```text
constraint references unknown metric gain_db
```

### Similar Metric Name Warning

If the objective or constraints reference an unknown metric but a declared
metric is similar under case-insensitive or punctuation-insensitive comparison,
doctor should produce a more specific message.

Example:

```text
objective expression references unknown metric P1DB; did you mean P1dB?
```

This should catch common user mistakes without silently correcting them.

The tool must not auto-rewrite the expression.

### Design Variable Semantic Check

Doctor should validate design variables beyond Pydantic shape:

- names are unique;
- `lower <= upper` for numeric-like values;
- `step > 0` when step exists;
- for stepped variables, the range should contain at least one value;
- fixed variables may be represented by `lower == upper` only if the current
  variable schema already accepts it; otherwise keep current schema behavior and
  report the existing validation error.

Values may include common SPICE suffixes such as:

```text
f, p, n, u, m, k, meg, g
```

If parsing fails because a bound is symbolic or unsupported, do not invent a
numeric conversion. Report a clear issue:

```text
variable W lower/upper/step must be numeric SPICE values for doctor range checks
```

### Remote Parallel Warning

For remote doctor, if `Spectre Settings.parallel_jobs` is greater than 8, doctor
should include a warning/check message:

```text
remote parallel_jobs=24 is high; normal remote multi-testbench runs should start around 4-8 to avoid SSH server limits
```

This should be warning-level if the report supports warnings. It should not
hard-fail doctor unless implementation cannot represent warnings safely.

Local doctor should not warn for `parallel_jobs > 8` by default because local
workstations/servers differ. This is specifically a remote SSH risk.

## Report Expectations

`reports/requirement_intake_report.json` should remain the primary evidence for
requirement checks.

Remote doctor should keep writing:

```text
REMOTE_PROJECT/reports/ic_opt_doctor_report.json
~/.ic-opt/remote_runs/<profile>/<hash>/reports/ic_opt_doctor_report.json
```

The requirement check entry inside remote doctor should include the semantic
issues/warnings generated by the same parser used locally.

## Agent Behavior After C-73

Agent skill should say:

- always run doctor before a fresh real run;
- if doctor fails, do not run `--real`;
- report exact issue messages from doctor;
- do not rewrite objective/OCEAN formulas unless the user explicitly asks;
- if doctor warns about remote `parallel_jobs`, recommend lowering to 4-8.

## Acceptance Criteria

- Local `check_requirement` fails undefined objective metric references.
- Remote `run_remote_doctor` reports the same undefined objective metric issue
  when parsing remote requirement text.
- Constraint references to unknown metrics fail doctor.
- Similar metric name suggestions are present for common case/style mismatches.
- Unsafe objective expressions fail without executing arbitrary code.
- Representative normalized FoM expressions pass dummy evaluation.
- Variable range semantic errors are detected before render/import.
- Remote high `parallel_jobs` produces a clear doctor message.
- Existing valid single-testbench and multi-testbench fixtures still pass.
- Existing product flow tests still pass.

## Verification Commands

Targeted:

```bash
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest \
  tests/test_requirement_intake.py \
  tests/test_remote_doctor.py \
  tests/test_product_cli_remote.py \
  -q
```

Full:

```bash
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest -q
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests tools --exclude tests/fixtures
rtk git -C ic-auto-opt-workflow-v0.1 diff --check
```
