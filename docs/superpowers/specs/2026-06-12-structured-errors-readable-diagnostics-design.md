# C-74 Structured Errors And Readable Diagnostics Design

Date: 2026-06-12

## Decision

Introduce a product-wide structured diagnostic layer for user-facing reports and
CLI failures.

The goal is not to add a new report-view command yet. The goal is to make
existing reports easier for both humans and agents to read:

- error code;
- severity;
- stage;
- component;
- short message;
- technical detail;
- likely cause;
- recommended action;
- evidence path or command when available.

The old `issues: list[str]` fields must remain for compatibility. New reports
should add structured diagnostics beside them instead of replacing them.

## Product Principle

Errors should be understandable without reading Python source.

For a normal IC user, an error should answer:

1. What failed?
2. Where did it fail?
3. Why did it probably fail?
4. What should I do next?
5. Which file/report/log proves this?

For an agent, an error should be machine-readable enough to decide:

- do not run real optimization;
- ask the user to fix `opt_requirement.md`;
- lower remote parallelism;
- inspect OCEAN logs;
- retry a real tool failure;
- stop and ask for user intervention.

## Current State

Most reports expose:

```json
{
  "status": "fail",
  "issues": [
    "objective expression references unknown metric P1DB; did you mean P1dB?"
  ]
}
```

This is useful but insufficient. A user or agent has to infer the stage,
severity, fix, and evidence.

Current affected areas include:

- requirement intake / doctor;
- remote doctor;
- product CLI errors;
- optimizer flow report;
- metric result checks;
- real result checks;
- optimizer decision/final summary;
- remote SSH/Spectre/OCEAN failures.

## Scope

C-74 should cover the product-facing error surface:

- `reports/requirement_intake_report.json`;
- `reports/ic_opt_doctor_report.json`;
- `reports/optimizer_flow_run_report.json`;
- `reports/metric_result_check_report.json`;
- `reports/real_run_check_report.json`;
- optimizer decision/final-summary reports where they already carry issues;
- CLI printing for `ic-opt --doctor`, `ic-opt --real`, and `ic-opt --continue`.

This is a schema/readability hardening task. It should not change optimizer
selection, Spectre/OCEAN execution, OpenBox behavior, or report generation
timing.

## Non-Goals

- Do not add a `show-report` or `view-report` command.
- Do not build a TUI.
- Do not rewrite all internal exceptions.
- Do not remove existing `issues`.
- Do not change status classifications such as `feasible`,
  `constraint_failed`, `metric_check_failed`, or `real_check_failed`.
- Do not run real simulations.
- Do not infer electrical root cause beyond evidence in existing reports/logs.

## Structured Diagnostic Schema

Add a small reusable model, likely in a dedicated module:

```python
class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"

class Diagnostic(BaseModel):
    code: str
    severity: DiagnosticSeverity
    stage: str
    component: str
    message: str
    detail: str | None = None
    likely_cause: str | None = None
    recommended_action: str | None = None
    evidence: list[str] = Field(default_factory=list)
```

Naming rules:

- `code` must be stable and uppercase snake case.
- `stage` should be one of a small controlled vocabulary:
  - `requirement`
  - `doctor`
  - `environment`
  - `remote_ssh`
  - `cadence`
  - `spectre`
  - `ocean`
  - `metric_check`
  - `optimizer`
  - `report`
- `component` should name the subsystem:
  - `requirement_intake`
  - `remote_doctor`
  - `product_cli`
  - `spectre_ocean_adapter`
  - `metric_results`
  - `optimizer_flow`
  - `optimizer_decision`

Reports should include:

```json
{
  "issues": ["legacy readable string"],
  "structured_issues": [
    {
      "code": "OBJECTIVE_UNKNOWN_METRIC",
      "severity": "error",
      "stage": "requirement",
      "component": "requirement_intake",
      "message": "Objective expression references unknown metric P1DB.",
      "detail": "Declared metrics include P1dB, but objective references P1DB.",
      "likely_cause": "Metric name mismatch in opt_requirement.md.",
      "recommended_action": "Change P1DB to P1dB, or rename the metric consistently.",
      "evidence": ["opt_requirement.md:Objective.expression"]
    }
  ]
}
```

## Compatibility Rules

1. Existing `issues` remains present.
2. Existing status values remain unchanged.
3. Existing tests that assert string issues should continue to pass unless
   deliberately updated to check both string and structured diagnostics.
4. New diagnostic fields should be additive.
5. JSON model validation must accept the new fields where appropriate.
6. CLI output may become more readable, but exit codes must not change.

## Minimum Error Catalog

C-74 should start with the errors users are already encountering.

### Requirement

- `OBJECTIVE_UNKNOWN_METRIC`
- `OBJECTIVE_UNSAFE_EXPRESSION`
- `OBJECTIVE_UNSUPPORTED_FUNCTION`
- `CONSTRAINT_UNKNOWN_METRIC`
- `VARIABLE_RANGE_INVALID`
- `REQUIREMENT_SECTION_MISSING`
- `REQUIREMENT_YAML_INVALID`
- `MAESTRO_INPUT_SCS_MISSING`

### Remote / Environment

- `SSH_LOGIN_FAILED`
- `REMOTE_PROJECT_MISSING`
- `REMOTE_PROJECT_NOT_WRITABLE`
- `REMOTE_PARALLELISM_HIGH`
- `CADENCE_CSHRC_MISSING`
- `CADENCE_TOOL_MISSING`

### Real Tool / Metric

- `SPECTRE_FAILED`
- `SPECTRE_ARTIFACT_MISSING`
- `OCEAN_FAILED`
- `OCEAN_SCALAR_MISSING`
- `METRIC_NON_SCALAR`
- `METRIC_NON_FINITE`
- `METRIC_MANIFEST_INVALID`

### Optimizer

- `NO_FEASIBLE_CANDIDATE`
- `NO_RECOMMENDED_CANDIDATE`
- `OPTIMIZER_REPORT_FAILED`
- `OPTIMIZER_ARTIFACT_MISSING`

## CLI Readability

For failures, `ic-opt` should print a compact readable block:

```text
doctor failed

[ERROR] OBJECTIVE_UNKNOWN_METRIC
Stage: requirement
Message: Objective expression references unknown metric P1DB.
Likely cause: Metric name mismatch in opt_requirement.md.
Action: Change P1DB to P1dB, or rename the metric consistently.
Evidence: opt_requirement.md:Objective.expression

Report: reports/requirement_intake_report.json
```

For warnings:

```text
[WARN] REMOTE_PARALLELISM_HIGH
Stage: remote_ssh
Message: remote parallel_jobs=24 is high.
Action: Start remote SSH runs around 4-8 parallel jobs.
```

CLI output should stay short. Long logs remain in report files.

## Agent Behavior After C-74

Agent skill should say:

- read `structured_issues` first when present;
- use `issues` as fallback for old reports;
- report code, stage, likely cause, and recommended action to the user;
- do not run `--real` when an error-severity diagnostic appears in doctor;
- warnings can be reported and may allow the workflow to continue if status is
  `pass`;
- do not silently edit formulas or variable ranges without explicit user
  approval.

## Acceptance Criteria

- Requirement unknown metric errors produce both legacy `issues` and
  `structured_issues`.
- Remote high parallel warning produces a structured warning diagnostic.
- Missing Cadence cshrc in product CLI produces a readable structured diagnostic
  or an equivalent structured CLI error wrapper.
- Existing doctor pass/fail behavior is unchanged.
- Existing report JSON remains backward-compatible.
- CLI failure output is easier to read than a raw Python exception or a single
  opaque string.
- Tests cover:
  - structured requirement semantic error;
  - structured close-name suggestion;
  - structured remote warning;
  - no structured errors on valid requirement;
  - legacy `issues` compatibility;
  - CLI failure formatting for at least one product-level error.

## Verification Commands

Targeted:

```bash
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest \
  tests/test_requirement_intake.py \
  tests/test_remote_doctor.py \
  tests/test_product_cli.py \
  tests/test_product_cli_remote.py \
  tests/test_agent_skill.py \
  -q
```

Full:

```bash
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest -q
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests tools --exclude tests/fixtures
rtk git -C ic-auto-opt-workflow-v0.1 diff --check
```
